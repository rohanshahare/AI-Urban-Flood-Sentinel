"""Unified response building: vision result -> risk engine -> API envelope.

No HTTP concerns here. Image analysis stays in `vision`, scoring stays in
`risk_engine`; this module only adapts one to the other.
"""
from __future__ import annotations

import math
import re
from typing import Any

from risk_engine.trend import assess_with_trend
from risk_engine.what_if import simulate

COMPLETED = "completed"
INCONCLUSIVE = "inconclusive"
ERROR = "error"

VISION_FIELDS = (
    "drain_id", "blockage_detected", "blockage_percentage", "confidence",
    "location", "timestamp", "method", "warnings",
)
ALERT_LEVELS = ("HIGH", "CRITICAL")
MANUAL_INSPECTION = (
    "Manual inspection required: the image could not be assessed reliably. "
    "This is NOT evidence that the drain is clear."
)
_DRAIN_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


class InputError(ValueError):
    """Invalid request metadata (maps to HTTP 400)."""


# ---------------------------------------------------------------- inputs

def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def _number(name: str, text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise InputError(f"{name} must be a number.") from None
    if not math.isfinite(value):
        raise InputError(f"{name} must be a finite number.")
    return value


def parse_drain_id(text: str | None) -> str | None:
    if _blank(text):
        return None
    text = text.strip()
    if not _DRAIN_ID.fullmatch(text):
        raise InputError("drain_id must be 1-64 characters: letters, digits, '.', '_' or '-'.")
    return text


def parse_location(lat: str | None, lon: str | None) -> dict[str, float] | None:
    """Both coordinates or neither; coordinates are never invented."""
    if _blank(lat) and _blank(lon):
        return None
    if _blank(lat) or _blank(lon):
        raise InputError("lat and lon must be supplied together.")
    lat_v, lon_v = _number("lat", lat), _number("lon", lon)
    if not -90 <= lat_v <= 90:
        raise InputError("lat must be between -90 and 90.")
    if not -180 <= lon_v <= 180:
        raise InputError("lon must be between -180 and 180.")
    return {"lat": lat_v, "lon": lon_v}


def parse_rainfall(text: str | None) -> float | None:
    """Rainfall in mm/day, or None when the caller supplied nothing."""
    if _blank(text):
        return None
    value = _number("rainfall_mm", text)
    if value < 0:
        raise InputError("rainfall_mm must not be negative.")
    return value


def _json_number(name: str, value: Any, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InputError(f"{name} must be a finite number.")
    return float(value)


def parse_scenario(body: Any, name: str) -> dict[str, float | None]:
    """Validate one side of a /simulate request: blockage 0-100, rainfall >= 0 or null."""
    if not isinstance(body, dict):
        raise InputError(f"{name} must be an object.")
    blockage = _json_number(f"{name}.blockage_percentage", body.get("blockage_percentage"))
    if not 0 <= blockage <= 100:
        raise InputError(f"{name}.blockage_percentage must be between 0 and 100.")
    rainfall = _json_number(f"{name}.rainfall_mm", body.get("rainfall_mm"), nullable=True)
    if rainfall is not None and rainfall < 0:
        raise InputError(f"{name}.rainfall_mm must not be negative.")
    return {"blockage_percentage": blockage, "rainfall": rainfall}


# --------------------------------------------------------------- shapes

def _empty_vision() -> dict[str, Any]:
    return {**dict.fromkeys(VISION_FIELDS), "warnings": []}


def _empty_risk(recommendation: str | None = None, warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "flood_risk_score": None,
        "risk_level": None,
        "risk_factors": [],
        "recommendation": recommendation,
        "warnings": warnings or [],
        "trend": {"direction": "UNKNOWN", "change": None, "previous_score": None},
        "inputs": None,
    }


def risk_view(result: dict[str, Any]) -> dict[str, Any]:
    """Public subset of a risk-engine result (no trend: the caller decides)."""
    return {k: result[k] for k in (
        "flood_risk_score", "risk_level", "risk_factors", "recommendation", "warnings", "inputs",
    )}


def _empty_alert() -> dict[str, Any]:
    return dict.fromkeys(("level", "title", "message", "recommendation")) | {"triggered": False}


def drain_record(drain_id, lat, lon, status, risk_level, score, blockage, synthetic, *,
                 recommendation=None, rainfall_source=None, synthetic_history=None) -> dict[str, Any]:
    """Summary of one drain. The last three fields let a list show why and on what inputs a level rests:
    rainfall_source is REQUEST | ASSUMED_DEFAULT | SYNTHETIC_DEMO | None; synthetic_history is bool or None."""
    return {
        "drain_id": drain_id, "lat": lat, "lon": lon,
        "processing_status": status, "risk_level": risk_level,
        "flood_risk_score": score, "blockage_percentage": blockage,
        "synthetic": synthetic, "recommendation": recommendation,
        "rainfall_source": rainfall_source, "synthetic_history": synthetic_history,
    }


def envelope(status, vision=None, risk=None, rainfall=None, alert=None, drain=None, error=None) -> dict[str, Any]:
    return {
        "processing_status": status,
        "vision": vision or _empty_vision(),
        "risk": risk or _empty_risk(),
        "rainfall": rainfall,
        "alert": alert or _empty_alert(),
        "drain": drain or drain_record(None, None, None, status, None, None, None, False),
        "error": error,
    }


def error_response(code: str, message: str, drain_id: str | None = None) -> dict[str, Any]:
    drain = drain_record(drain_id, None, None, ERROR, None, None, None, False)
    return envelope(ERROR, drain=drain, error={"code": code, "message": message})


# ------------------------------------------------------------- pipeline

def _alert_for(risk: dict[str, Any]) -> dict[str, Any]:
    level = risk["risk_level"]
    suffix = " Based partly on SYNTHETIC data." if risk["inputs"]["synthetic_data"] else ""
    return {
        "triggered": level in ALERT_LEVELS,
        "level": level,
        "title": f"{level} drainage-related flood risk",
        "message": f"Estimated risk score {risk['flood_risk_score']}/100 (experimental estimate).{suffix}",
        "recommendation": risk["recommendation"],
    }


def process_vision_result(
    vision: dict[str, Any],
    rainfall_mm: float | None,
    location: dict[str, float] | None,
) -> dict[str, Any]:
    """Turn a vision result into a completed or inconclusive envelope.

    A null blockage percentage never reaches the scoring function.
    """
    vision = {**_empty_vision(), **{k: vision.get(k) for k in VISION_FIELDS}}
    drain_id = vision["drain_id"]
    lat, lon = (location["lat"], location["lon"]) if location else (None, None)
    percentage = vision["blockage_percentage"]
    request_rain = (
        {"mm_per_day": rainfall_mm, "category": None, "source": "REQUEST"}
        if rainfall_mm is not None else None
    )

    if percentage is None:
        # Vision reports null for both "uncertain" and "no blockage seen";
        # neither is proof of a clear drain, so blockage_detected is nulled.
        vision["blockage_detected"] = None
        risk = _empty_risk(
            MANUAL_INSPECTION,
            ["Vision assessment inconclusive: no usable blockage percentage, so no risk score was calculated."],
        )
        alert = _empty_alert()
        alert.update(
            title="Manual inspection required",
            message="The image could not be assessed reliably; no flood-risk level is available.",
            recommendation=MANUAL_INSPECTION,
        )
        drain = drain_record(drain_id, lat, lon, INCONCLUSIVE, None, None, None, False,
                             recommendation=MANUAL_INSPECTION,
                             rainfall_source="REQUEST" if rainfall_mm is not None else None)
        return envelope(INCONCLUSIVE, vision, risk, request_rain, alert, drain)

    result = assess_with_trend({
        "drain_id": drain_id,
        "blockage_percentage": percentage,
        "rainfall": rainfall_mm,
        "confidence": vision["confidence"],
    })
    if result["status"] != "OK":
        raise RuntimeError("; ".join(result["warnings"]) or "risk engine rejected the input")

    risk = {**risk_view(result), "trend": result["trend"]}
    rain_inputs = result["inputs"]
    rainfall = {
        "mm_per_day": rainfall_mm,
        "category": rain_inputs["rainfall_category"],
        "source": "REQUEST" if rain_inputs["rainfall_source"] == "PROVIDED" else "ASSUMED_DEFAULT",
    }
    drain = drain_record(
        drain_id, lat, lon, COMPLETED, risk["risk_level"],
        risk["flood_risk_score"], percentage, False,
        recommendation=risk["recommendation"], rainfall_source=rainfall["source"],
        synthetic_history=rain_inputs["synthetic_data"],
    )
    return envelope(COMPLETED, vision, risk, rainfall, _alert_for(risk), drain)


def simulation_response(body: Any) -> dict[str, Any]:
    """Hypothetical what-if comparison. Never an alert, never stored, never logged to trend."""
    if not isinstance(body, dict):
        raise InputError("Request body must be a JSON object.")
    drain_id = parse_drain_id(body.get("drain_id") if isinstance(body.get("drain_id"), str) else None)
    baseline = parse_scenario(body.get("baseline"), "baseline")
    scenario = parse_scenario(body.get("scenario"), "scenario")
    result = simulate({"drain_id": drain_id, **baseline}, scenario)
    return {
        "simulation": True,
        "label": "HYPOTHETICAL SIMULATION - not a prediction and not an alert.",
        "drain_id": drain_id,
        "baseline": risk_view(result["baseline"]),
        "scenario": risk_view(result["scenario"]),
        "change": result["change"],
    }
