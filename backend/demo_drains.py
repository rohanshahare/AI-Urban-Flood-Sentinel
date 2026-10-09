"""SYNTHETIC demonstration drains for the dashboard map.

Every coordinate, blockage value and rainfall value below is invented for the
demo. Risk values are computed by the real risk engine from these inputs;
none of it is an observation of a real drain, and none of it raises an alert.
"""
from __future__ import annotations

from risk_engine.history import assess_with_history

from .pipeline import COMPLETED, INCONCLUSIVE, _empty_alert, _empty_risk, _empty_vision, drain_record, envelope, risk_view

DEMO_INCONCLUSIVE = "Manual inspection required: no usable blockage estimate in this demo record."
DEMO_NOTE = "Synthetic demo record: blockage and rainfall values are invented; no image was analysed."

# (drain_id, lat, lon, blockage %, rainfall mm/day). None = not available.
_DEMO = [
    ("D-001", 12.9750, 77.5900, 85, 120),
    ("D-002", 12.9770, 77.6050, 10, 5),
    ("D-003", 12.9690, 77.6010, 55, 40),
    ("D-005", 12.9800, 77.5990, None, 40),  # inconclusive vision result
    ("D-006", 12.9650, 77.5880, 35, 70),
    ("D-010", None, None, 20, 10),          # no coordinates: listed, never plotted
    ("D-017", 12.9720, 77.5950, 82, 90),
]


def _score(drain_id, blockage, rain):
    # assess_with_history, not assess_with_trend: listing demo drains must not write trend history.
    return assess_with_history({"drain_id": drain_id, "blockage_percentage": blockage, "rainfall": rain})


def _record(drain_id, lat, lon, blockage, rain) -> dict:
    if blockage is None:
        return drain_record(drain_id, lat, lon, INCONCLUSIVE, None, None, None, True,
                            recommendation=DEMO_INCONCLUSIVE, rainfall_source="SYNTHETIC_DEMO")
    result = _score(drain_id, blockage, rain)
    return drain_record(drain_id, lat, lon, COMPLETED, result["risk_level"],
                        result["flood_risk_score"], float(blockage), True,
                        recommendation=result["recommendation"], rainfall_source="SYNTHETIC_DEMO",
                        synthetic_history=result["inputs"]["synthetic_data"])


def demo_records() -> list[dict]:
    return [_record(*row) for row in _DEMO]


def demo_detail(drain_id: str) -> dict | None:
    """Full envelope for one demo drain (risk breakdown only; no vision analysis exists)."""
    row = next((r for r in _DEMO if r[0] == drain_id), None)
    if row is None:
        return None
    _, _, _, blockage, rain = row
    record = _record(*row)
    vision = {**_empty_vision(), "drain_id": drain_id, "method": "SYNTHETIC DEMO RECORD (no image analysed)",
              "warnings": [DEMO_NOTE]}
    alert = {**_empty_alert(), "title": "Synthetic demo record", "message": "Demo records never raise operational alerts."}
    if blockage is None:
        risk = _empty_risk(DEMO_INCONCLUSIVE)
        return envelope(INCONCLUSIVE, vision, risk, None, alert, record)
    result = _score(drain_id, blockage, rain)
    vision["blockage_percentage"] = float(blockage)
    risk = {**risk_view(result), "trend": {"direction": "UNKNOWN", "change": None, "previous_score": None}}
    rainfall = {"mm_per_day": float(rain), "category": result["inputs"]["rainfall_category"], "source": "SYNTHETIC_DEMO"}
    return envelope(COMPLETED, vision, risk, rainfall, alert, record)
