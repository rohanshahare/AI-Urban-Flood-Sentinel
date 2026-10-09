
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from risk_engine.trend import assess_with_trend, reset_log


def test_trend():
    reset_log()
    base = {"drain_id": "D-017", "blockage_percentage": 82}

    r = assess_with_trend({**base, "rainfall": 10})
    assert r["trend"]["direction"] == "NEW"

    r = assess_with_trend({**base, "rainfall": 90})
    assert r["trend"]["direction"] == "RISING"
    assert r["trend"]["change"] > 0

    r = assess_with_trend({**base, "rainfall": 90})
    assert r["trend"]["direction"] == "STABLE"
    assert r["trend"]["change"] == 0

    r = assess_with_trend({**base, "rainfall": 10})
    assert r["trend"]["direction"] == "FALLING"

    r = assess_with_trend({
        "drain_id": "D-017",
        "blockage_percentage": 150,
    })
    assert r["status"] == "ERROR"
    assert r["trend"]["direction"] == "UNKNOWN"

    print("Trend tests passed!")


if __name__ == "__main__":
    test_trend()
