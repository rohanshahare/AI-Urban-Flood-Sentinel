"""FastAPI backend: image upload -> vision -> risk engine -> unified response.

Run from the repository root:
    python -m uvicorn backend.main:app --reload
"""
from __future__ import annotations

import asyncio
import logging
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
from .demo_drains import demo_records

ROOT = Path(__file__).resolve().parents[1]
OLLAMA_URL = os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL)
VISION_MODEL = os.environ.get("VISION_MODEL", DEFAULT_MODEL)
VISION_TIMEOUT = float(os.environ.get("VISION_TIMEOUT", "180"))
MAX_IMAGE_BYTES = DEFAULT_MAX_IMAGE_BYTES
MAX_UPLOADED_DRAINS = 100

log = logging.getLogger("flood_sentinel")
app = FastAPI(title="AI Urban Flood Sentinel", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])

# shortcut: in-memory, lost on restart; upgrade to a database if records must persist.
_UPLOADED: OrderedDict[str, dict] = OrderedDict()


def _error(status_code: int, code: str, message: str, drain_id: str | None = None) -> JSONResponse:
    return JSONResponse(pipeline.error_response(code, message, drain_id), status_code=status_code)


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


@app.get("/drains")
def drains() -> list[dict]:
    """SYNTHETIC demo drains, with any drains analysed via /analyze this session."""
    merged = {r["drain_id"]: r for r in demo_records()}
    merged.update(_UPLOADED)
    return list(merged.values())


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
        _UPLOADED[parsed_id] = response["drain"]
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
