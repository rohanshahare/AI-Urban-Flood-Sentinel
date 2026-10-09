
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from risk_engine.engine import assess_flood_risk as run

def test_all():
    r = run({"drain_id": "A", "blockage_percentage": 15, "rainfall": 10, "history": "LOW"})
    assert r["risk_level"] == "LOW" and r["flood_risk_score"] == 20

    r = run({"drain_id": "B", "blockage_percentage": 50, "rainfall": 40, "history": "MEDIUM"})
    assert r["flood_risk_score"] == 52 and r["risk_level"] in ("MODERATE", "HIGH")

    r = run({"drain_id": "C", "blockage_percentage": 90, "rainfall": 150, "history": "HIGH"})
    assert r["risk_level"] == "CRITICAL" and abs(r["flood_risk_score"] - 94) <= 1

    r = run({"drain_id": "D", "blockage_percentage": 82, "rainfall": "Heavy"})  # no history
    assert r["risk_level"] == "CRITICAL" and r["flood_risk_score"] == 81
    assert any("Historical data unavailable" in w for w in r["warnings"])

    r = run({"drain_id": "E", "blockage_percentage": 82, "history": "HIGH"})    # no rainfall
    assert r["status"] == "OK" and any("assumed" in w.lower() for w in r["warnings"])

    for bad in (150, "abc", None):
        r = run({"drain_id": "F", "blockage_percentage": bad})
        assert r["status"] == "ERROR" and r["flood_risk_score"] is None

    r = run({"drain_id": "G", "blockage_percentage": 60, "rainfall": 30, "confidence": 0.3})
    assert any("manual verification" in w.lower() for w in r["warnings"])

    print("All tests passed")

if __name__ == "__main__":
    test_all()