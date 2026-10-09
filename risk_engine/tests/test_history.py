
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from risk_engine.history import assess_with_history, vulnerability_label


def test_history():
    assert vulnerability_label(3, 6, True) == "HIGH"
    assert vulnerability_label(0, 0, False) == "LOW"

    result = assess_with_history({
        "drain_id": "D-017",
        "blockage_percentage": 82,
        "rainfall": 80,
    })

    print("D-017:", result)

    assert result["risk_level"] == "CRITICAL"
    assert any(
        "SYNTHETIC" in warning
        for warning in result["warnings"]
    )

    result = assess_with_history({
        "drain_id": "D-999",
        "blockage_percentage": 82,
        "rainfall": 80,
    })

    print("D-999:", result)

    assert result["status"] == "OK"
    assert any(
        "Historical data unavailable" in warning
        for warning in result["warnings"]
    )

    print("History tests passed!")


if __name__ == "__main__":
    test_history()
