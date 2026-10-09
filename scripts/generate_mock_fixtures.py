"""Regenerate mock/*.json in the canonical API shape.

Run from the repository root:  python scripts/generate_mock_fixtures.py

Fixtures are produced by the real pipeline and risk engine from invented
vision outputs, so mock mode cannot drift from the API contract. They are
labelled synthetic: no image is analysed and nothing here is a real finding.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import pipeline  # noqa: E402
from backend.demo_drains import demo_records  # noqa: E402
from risk_engine.trend import reset_log  # noqa: E402

OUT = ROOT / "mock"
STAMP = "2026-10-09T00:00:00Z"
MOCK_METHOD = "SYNTHETIC MOCK FIXTURE (no image analysed)"
MOCK_WARNING = "Mock fixture: invented vision output used to exercise the interface. Not a real finding."


def vision_output(drain_id, percentage, **extra):
    return {
        "drain_id": drain_id, "blockage_detected": percentage is not None, "blockage_percentage": percentage,
        "confidence": None, "location": None, "timestamp": STAMP, "method": MOCK_METHOD,
        "warnings": [MOCK_WARNING, *extra.get("warnings", [])],
    }


def mock_envelope(drain_id, percentage, rainfall_mm, lat, lon, **extra):
    env = pipeline.process_vision_result(vision_output(drain_id, percentage, **extra), rainfall_mm, {"lat": lat, "lon": lon})
    env["drain"]["synthetic"] = True  # the dashboard adds its own "[MOCK]" prefix to alerts
    return env


def build_fixtures() -> dict[str, object]:
    """All fixtures as Python data, keyed by file stem. Writes nothing."""
    reset_log()
    fixtures = {
        "completed-critical": mock_envelope("D-001", 90.0, 150, 12.9750, 77.5900),
        "completed-low": mock_envelope("D-002", 10.0, 5, 12.9770, 77.6050),
        "inconclusive": mock_envelope(
            "D-005", None, 40, 12.9800, 77.5990,
            warnings=["Drain opening is not clearly visible."],
        ),
        "error": pipeline.error_response(
            "VISION_SERVICE_ERROR", "Mock fixture: the vision service is unavailable.", "D-ERR"),
        "drains": demo_records(),
    }
    reset_log()  # fixtures must not leave trend history behind
    return fixtures


def serialize(data: object) -> str:
    return json.dumps(data, indent=2) + "\n"


def main(out: Path = OUT) -> None:
    """Write the fixtures to `out` (the real mock/ directory only when run as a script)."""
    out.mkdir(exist_ok=True)
    for name, data in build_fixtures().items():
        (out / f"{name}.json").write_text(serialize(data), encoding="utf-8")
        print("wrote", out / f"{name}.json")


if __name__ == "__main__":
    main()
