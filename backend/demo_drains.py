"""SYNTHETIC demonstration drains for the dashboard map.

Every coordinate, blockage value and rainfall value below is invented for the
demo. Risk values are computed by the real risk engine from these inputs;
none of it is an observation of a real drain.
"""
from __future__ import annotations

from risk_engine.history import assess_with_history

from .pipeline import COMPLETED, INCONCLUSIVE, drain_record

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


def demo_records() -> list[dict]:
    records = []
    for drain_id, lat, lon, blockage, rain in _DEMO:
        if blockage is None:
            records.append(drain_record(drain_id, lat, lon, INCONCLUSIVE, None, None, None, True))
            continue
        result = assess_with_history(
            {"drain_id": drain_id, "blockage_percentage": blockage, "rainfall": rain}
        )
        records.append(drain_record(
            drain_id, lat, lon, COMPLETED, result["risk_level"],
            result["flood_risk_score"], float(blockage), True,
        ))
    return records
