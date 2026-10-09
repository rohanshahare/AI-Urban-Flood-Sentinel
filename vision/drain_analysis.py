"""Experimental drain-image assessment using a local Ollama vision model.

This module provides an integration-friendly baseline, not a validated
blockage detector. Model estimates are qualitative and must be reviewed.
Only the Python standard library is required.
"""
from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

DEFAULT_MODEL = "gemma3:12b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_MAX_IMAGE_BYTES = 10 * 1024 * 1024

class VisionInputError(ValueError):
    """Raised when the supplied image or metadata is invalid."""

class VisionServiceError(RuntimeError):
    """Raised when Ollama is unreachable or returns an unusable response."""

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "drain_visible": {"type": "boolean"},
        "image_quality": {"type": "string", "enum": ["good", "fair", "poor"]},
        "blockage_detected": {"type": "boolean"},
        "blockage_percentage": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
        "assessment_uncertain": {"type": "boolean"},
        "observations": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "drain_visible", "image_quality", "blockage_detected",
        "blockage_percentage", "assessment_uncertain", "observations", "warnings"
    ],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = """You are assisting with visual maintenance triage for urban drains.
Inspect only evidence visible in the supplied image. Do not infer flood timing,
hidden conditions, or facts not visible. Determine whether there is visible
evidence that material obstructs the actual drain opening, rather than simply
being nearby. If no drain or opening is visible, or image quality prevents a
reliable assessment, set blockage_detected=false, blockage_percentage=null,
assessment_uncertain=true, and explain the limitation in warnings.
Only estimate blockage_percentage when the drain opening is clearly visible
and its visibly obstructed area can be approximated; otherwise return null.
This is a rough visual estimate, not a calibrated measurement. Do not produce
a confidence score. Return only the JSON required by the supplied schema."""


def _read_image(image: str | os.PathLike[str] | bytes | bytearray | BinaryIO,
                max_image_bytes: int) -> tuple[bytes, str]:
    """Read image bytes from a path, bytes-like object, or binary file object."""
    filename: str | None = None
    try:
        if isinstance(image, (str, os.PathLike)):
            path = Path(image).expanduser()
            if not path.is_file():
                raise VisionInputError(f"Image file does not exist or is not a file: {path}")
            filename = path.name
            data = path.read_bytes()
        elif isinstance(image, (bytes, bytearray)):
            data = bytes(image)
        elif hasattr(image, "read"):
            data = image.read(max_image_bytes + 1)
            filename = getattr(image, "name", None)
            if not isinstance(data, (bytes, bytearray)):
                raise VisionInputError("Image file object must return bytes when read.")
            data = bytes(data)
        else:
            raise VisionInputError("image must be a file path, bytes, or binary file object.")
    except VisionInputError:
        raise
    except (OSError, ValueError) as exc:
        raise VisionInputError(f"Unable to read image: {exc}") from exc

    if not data:
        raise VisionInputError("Image is empty.")
    if len(data) > max_image_bytes:
        raise VisionInputError(
            f"Image exceeds the {max_image_bytes // (1024 * 1024)} MiB size limit."
        )

    image_format = _detect_image_format(data)
    if image_format is None:
        raise VisionInputError("Unsupported or unrecognized image format. Use PNG, JPEG, WebP, GIF, or BMP.")

    mime = mimetypes.guess_type(filename or "")[0]
    if not mime or not mime.startswith("image/"):
        mime = image_format
    return data, mime


def _detect_image_format(data: bytes) -> str | None:
    """Recognize common image signatures; actual decoding is performed by Ollama."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    return None


def _call_ollama(image_b64: str, model: str, base_url: str, timeout: float) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    payload = {
        "model": model,
        "stream": False,
        "format": _RESPONSE_SCHEMA,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Assess this drain image for visible blockage. Be conservative. "
                    "Do not treat debris outside the opening as blockage."
                ),
                "images": [image_b64],
            },
        ],
    }
    request = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise VisionServiceError(
            f"Could not reach Ollama at {base_url}. Ensure Ollama is running and model '{model}' is installed. Details: {reason}"
        ) from exc
    except TimeoutError as exc:
        raise VisionServiceError(f"Ollama request timed out after {timeout:g} seconds.") from exc

    try:
        envelope = json.loads(body)
        content = envelope["message"]["content"]
        result = json.loads(content)
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise VisionServiceError("Ollama returned a response that was not valid structured JSON.") from exc

    if not isinstance(result, dict):
        raise VisionServiceError("Ollama result must be a JSON object.")
    return result


def analyze_drain(
    image: str | os.PathLike[str] | bytes | bytearray | BinaryIO,
    *,
    drain_id: str | None = None,
    location: dict[str, float] | None = None,
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
) -> dict[str, Any]:
    """Analyze a drain image using a local Ollama multimodal model.

    Args:
        image: Image file path, raw image bytes, or binary file object.
        drain_id: Optional drain identifier.
        location: Optional coordinates, normally {"lat": float, "lon": float}.
        model: Installed Ollama vision-capable model; defaults to gemma3:12b.
        ollama_url: Base URL for local Ollama service.
        timeout: Request timeout in seconds.
        max_image_bytes: Maximum accepted encoded image size.

    Returns:
        A dictionary matching the vision result contract. ``confidence`` is
        always None because this model response is not calibrated.

    Raises:
        VisionInputError: Invalid image or metadata.
        VisionServiceError: Ollama unavailable or malformed model response.
    """
    if drain_id is not None and not isinstance(drain_id, str):
        raise VisionInputError("drain_id must be a string or None.")
    if location is not None:
        if not isinstance(location, dict):
            raise VisionInputError('location must be a dictionary with "lat" and "lon", or None.')
        if set(location) != {"lat", "lon"}:
            raise VisionInputError('location must contain exactly "lat" and "lon".')
        for key in ("lat", "lon"):
            value = location[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise VisionInputError(f'location["{key}"] must be numeric.')
        if not -90 <= location["lat"] <= 90:
            raise VisionInputError('location["lat"] must be between -90 and 90.')
        if not -180 <= location["lon"] <= 180:
            raise VisionInputError('location["lon"] must be between -180 and 180.')
    if not isinstance(model, str) or not model.strip():
        raise VisionInputError("model must be a non-empty string.")
    if timeout <= 0:
        raise VisionInputError("timeout must be positive.")
    if max_image_bytes <= 0:
        raise VisionInputError("max_image_bytes must be positive.")

    image_bytes, _mime = _read_image(image, max_image_bytes)
    result = _call_ollama(base64.b64encode(image_bytes).decode("ascii"), model, ollama_url, timeout)

    required = {
        "drain_visible", "image_quality", "blockage_detected", "blockage_percentage",
        "assessment_uncertain", "observations", "warnings"
    }
    if not required.issubset(result):
        raise VisionServiceError("Model response is missing required analysis fields.")
    if not isinstance(result["blockage_detected"], bool):
        raise VisionServiceError("Model returned an invalid blockage_detected value.")
    if not isinstance(result["assessment_uncertain"], bool):
        raise VisionServiceError("Model returned an invalid assessment_uncertain value.")
    if result["image_quality"] not in {"good", "fair", "poor"}:
        raise VisionServiceError("Model returned an invalid image_quality value.")
    if not isinstance(result["warnings"], list) or not all(isinstance(w, str) for w in result["warnings"]):
        raise VisionServiceError("Model returned invalid warnings.")

    percentage = result["blockage_percentage"]
    if percentage is not None:
        if isinstance(percentage, bool) or not isinstance(percentage, (int, float)) or not 0 <= percentage <= 100:
            raise VisionServiceError("Model returned blockage_percentage outside the valid 0-100 range.")
        percentage = round(float(percentage), 1)

    blockage_detected = result["blockage_detected"] and result["drain_visible"] and not result["assessment_uncertain"]
    warnings = list(result["warnings"])
    warnings.append("Experimental vision-language assessment; validate against labelled drain images before operational use.")
    if result["assessment_uncertain"] or not result["drain_visible"] or result["image_quality"] == "poor":
        warnings.append("Assessment is uncertain or the drain opening is not clearly visible; do not interpret a negative result as proof that the drain is clear.")
        percentage = None
    if not blockage_detected:
        # A percentage is meaningful only when the model actually identified a visible blockage.
        percentage = None

    return {
        "drain_id": drain_id,
        "blockage_detected": bool(blockage_detected),
        "blockage_percentage": percentage,
        "confidence": None,
        "location": dict(location) if location is not None else None,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "method": f"Local Ollama multimodal model ({model}); qualitative visual assessment; confidence is not calibrated.",
        "warnings": warnings,
    }
