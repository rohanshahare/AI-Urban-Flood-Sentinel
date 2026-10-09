"""FastAPI backend: image upload -> vision -> risk engine -> unified response.

Run from the repository root:
    python -m uvicorn backend.main:app --reload
"""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from vision import VisionInputError, VisionServiceError, analyze_drain
from vision.drain_analysis import DEFAULT_MAX_IMAGE_BYTES, DEFAULT_MODEL, DEFAULT_OLLAMA_URL

from . import pipeline
from .demo_drains import demo_detail, demo_records

ROOT = Path(__file__).resolve().parents[1]
OLLAMA_URL = os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL)
VISION_MODEL = os.environ.get("VISION_MODEL", DEFAULT_MODEL)
VISION_TIMEOUT = float(os.environ.get("VISION_TIMEOUT", "180"))
MAX_IMAGE_BYTES = DEFAULT_MAX_IMAGE_BYTES
MAX_UPLOADED_DRAINS = 100
# multipart overhead allowance on top of the image limit, for the Content-Length pre-check
UPLOAD_OVERHEAD_BYTES = 64 * 1024

# Windows registries sometimes map .js to text/plain, which breaks ES-module loading.
mimetypes.add_type("text/javascript", ".js")

log = logging.getLogger("flood_sentinel")
app = FastAPI(title="AI Urban Flood Sentinel", version="0.1.0")
# Local prototype: the dashboard is served same-origin, so CORS only needs to admit
# a dashboard opened from another local port (e.g. a static file server). No auth.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# shortcut: in-memory, lost on restart, capped; upgrade to a database if records must persist.
_UPLOADED: OrderedDict[str, dict] = OrderedDict()  # drain_id -> full response envelope


def _error(status_code: int, code: str, message: str, drain_id: str | None = None) -> JSONResponse:
    return JSONResponse(pipeline.error_response(code, message, drain_id), status_code=status_code)


def _too_large_body() -> bytes:
    message = f"Image exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)} MiB limit."
    return json.dumps(pipeline.error_response("IMAGE_TOO_LARGE", message)).encode()


class UploadLimitMiddleware:
    """Caps the /analyze request body while it streams in, before multipart parsing finishes.

    A declared Content-Length over the limit is refused without reading the body. Otherwise
    (including chunked uploads with no Content-Length) bytes are counted as they arrive; once
    the limit is crossed the body is cut off and the response is replaced by a 413 envelope.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/analyze":
            return await self.app(scope, receive, send)
        limit = MAX_IMAGE_BYTES + UPLOAD_OVERHEAD_BYTES  # read per request so tests can patch it
        length = dict(scope["headers"]).get(b"content-length", b"")
        if length.isdigit() and int(length) > limit:
            return await self._reject(send)

        state = {"received": 0, "too_large": False, "replied": False}

        async def counting_receive():
            if state["too_large"]:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                state["received"] += len(message.get("body", b""))
                if state["received"] > limit:
                    state["too_large"] = True
                    return {"type": "http.disconnect"}  # stops the multipart parser
            return message

        async def guarded_send(message):
            if not state["too_large"]:
                return await send(message)
            if message["type"] == "http.response.start" and not state["replied"]:
                await self._reject(send)  # replace whatever error the parser produced
            state["replied"] = True

        try:
            await self.app(scope, counting_receive, guarded_send)
        except Exception:
            if not state["too_large"]:
                raise
        if state["too_large"] and not state["replied"]:
            await self._reject(send)

    @staticmethod
    async def _reject(send):
        body = _too_large_body()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


app.add_middleware(UploadLimitMiddleware)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError):
    fields = ", ".join(sorted({str(e["loc"][-1]) for e in exc.errors()}))
    return _error(422, "INVALID_REQUEST", f"Invalid or missing request field(s): {fields}.")


@app.exception_handler(StarletteHTTPException)
async def _http_error(_: Request, exc: StarletteHTTPException):
    code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
    return _error(exc.status_code, code, str(exc.detail))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Endpoints below are `async def` on purpose: they are fast, and running on the event
# loop thread means they never iterate _UPLOADED while /analyze mutates it.
@app.get("/drains")
async def drains() -> list[dict]:
    """SYNTHETIC demo drains, with any drains analysed via /analyze this session."""
    merged = {r["drain_id"]: r for r in demo_records()}
    merged.update({k: v["drain"] for k, v in _UPLOADED.items()})
    return list(merged.values())


@app.get("/drains/{drain_id}")
async def drain_detail(drain_id: str):
    """Full envelope for one drain: the stored analysis, else a synthetic demo breakdown."""
    detail = _UPLOADED.get(drain_id) or demo_detail(drain_id)
    if detail is None:
        return _error(404, "NOT_FOUND", "Unknown drain.", None)
    return detail


_SCENARIO_SCHEMA = {
    "type": "object", "required": ["blockage_percentage"],
    "properties": {"blockage_percentage": {"type": "number", "minimum": 0, "maximum": 100},
                   "rainfall_mm": {"type": ["number", "null"], "minimum": 0, "description": "mm/day; null = assumed default"}},
}
_SIMULATE_DOC = {"requestBody": {"required": True, "content": {"application/json": {
    "schema": {"type": "object", "required": ["baseline", "scenario"],
               "properties": {"drain_id": {"type": "string", "description": "Optional; selects synthetic history"},
                              "baseline": _SCENARIO_SCHEMA, "scenario": _SCENARIO_SCHEMA}},
    "example": {"drain_id": "D-017", "baseline": {"blockage_percentage": 82, "rainfall_mm": 90},
                "scenario": {"blockage_percentage": 40, "rainfall_mm": 30}}}}}}


# Validation stays in pipeline.simulation_response (400 + error envelope); the schema above is documentation.
@app.post("/simulate", openapi_extra=_SIMULATE_DOC)
async def simulate(request: Request):
    """Hypothetical what-if. Reuses the risk engine; no alert, no storage, no trend entry."""
    try:
        body = await request.json()
    except ValueError:
        return _error(400, "INVALID_INPUT", "Request body must be valid JSON.")
    try:
        return pipeline.simulation_response(body)
    except pipeline.InputError as exc:
        return _error(400, "INVALID_INPUT", str(exc))
    except ValueError as exc:
        log.warning("Simulation rejected by risk engine: %s", exc)
        return _error(400, "INVALID_INPUT", "Scenario could not be scored.")


@app.post("/analyze")
async def analyze(
    image: UploadFile = File(...),
    drain_id: str | None = Form(None),
    lat: str | None = Form(None),
    lon: str | None = Form(None),
    rainfall_mm: str | None = Form(None),
):
    parsed_id = None
    try:
        parsed_id = pipeline.parse_drain_id(drain_id)
        location = pipeline.parse_location(lat, lon)
        rainfall = pipeline.parse_rainfall(rainfall_mm)
    except pipeline.InputError as exc:
        return _error(400, "INVALID_INPUT", str(exc), parsed_id)

    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        return _error(413, "IMAGE_TOO_LARGE", f"Image exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)} MiB limit.", parsed_id)

    try:
        # Blocking HTTP call to Ollama: keep it off the event loop.
        vision = await asyncio.to_thread(
            analyze_drain, data,
            drain_id=parsed_id, location=location,
            model=VISION_MODEL, ollama_url=OLLAMA_URL, timeout=VISION_TIMEOUT,
            max_image_bytes=MAX_IMAGE_BYTES,
        )
    except VisionInputError as exc:
        return _error(400, "INVALID_INPUT", str(exc), parsed_id)
    except VisionServiceError as exc:
        log.warning("Vision service failure: %s", exc)
        return _error(
            502, "VISION_SERVICE_ERROR",
            "The vision service is unavailable or returned an unusable response. "
            "The drain was not assessed; this is not a clear-drain result.",
            parsed_id,
        )

    try:
        response = pipeline.process_vision_result(vision, rainfall, location)
    except Exception:
        log.exception("Risk engine failure")
        return _error(500, "RISK_ENGINE_ERROR", "Risk assessment failed.", parsed_id)

    if parsed_id:
        _UPLOADED[parsed_id] = response
        _UPLOADED.move_to_end(parsed_id)
        if len(_UPLOADED) > MAX_UPLOADED_DRAINS:
            _UPLOADED.popitem(last=False)
    return response


@app.exception_handler(Exception)
async def _unexpected(_: Request, exc: Exception):
    log.exception("Unhandled error", exc_info=exc)
    return _error(500, "INTERNAL_ERROR", "Unexpected server error.")


# Serve the dashboard (explicit paths only, so .git/.venv/data are never exposed).
@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(ROOT / "index.html")


app.mount("/css", StaticFiles(directory=ROOT / "css"), name="css")
app.mount("/js", StaticFiles(directory=ROOT / "js"), name="js")
app.mount("/mock", StaticFiles(directory=ROOT / "mock"), name="mock")  # explicit-opt-in mock fixtures
app.mount("/samples", StaticFiles(directory=ROOT / "data"), name="samples")  # sample images + licence notes
