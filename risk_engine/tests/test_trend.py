import unittest

from risk_engine import trend
from risk_engine.history import assess_with_history
from risk_engine.trend import assess_with_trend, reset_log

KNOWN = {"rainfall": 20, "history": "LOW"}


def reading(drain_id, blockage):
    return {"drain_id": drain_id, "blockage_percentage": blockage, **KNOWN}


def blockage_for_delta(base_blockage, delta):
    """Find a blockage value whose score differs from the base by exactly delta."""
    base = assess_with_history(reading("X", base_blockage))["flood_risk_score"]
    for b in range(base_blockage, 101):
        if assess_with_history(reading("X", b))["flood_risk_score"] - base == delta:
            return b
    raise AssertionError(f"no blockage gives delta {delta}")


class TrendTests(unittest.TestCase):
    def setUp(self):
        reset_log()

    def test_sequence(self):
        base = {"drain_id": "D-017", "blockage_percentage": 82}
        r = assess_with_trend({**base, "rainfall": 10})
        self.assertEqual(r["trend"], {"direction": "NEW", "change": None, "previous_score": None})
        first = r["flood_risk_score"]

        r = assess_with_trend({**base, "rainfall": 90})
        self.assertEqual(r["trend"]["direction"], "RISING")
        self.assertEqual(r["trend"]["previous_score"], first)
        self.assertEqual(r["trend"]["change"], r["flood_risk_score"] - first)

        r = assess_with_trend({**base, "rainfall": 90})
        self.assertEqual((r["trend"]["direction"], r["trend"]["change"]), ("STABLE", 0))

        r = assess_with_trend({**base, "rainfall": 10})
        self.assertEqual(r["trend"]["direction"], "FALLING")

    def test_threshold_boundaries(self):
        for delta, rising, falling in ((4, "STABLE", "STABLE"), (5, "RISING", "FALLING")):
            high = blockage_for_delta(40, delta)
            reset_log()
            assess_with_trend(reading("B", 40))
            r = assess_with_trend(reading("B", high))
            self.assertEqual((r["trend"]["change"], r["trend"]["direction"]), (delta, rising))
            reset_log()
            assess_with_trend(reading("B", high))
            r = assess_with_trend(reading("B", 40))
            self.assertEqual((r["trend"]["change"], r["trend"]["direction"]), (-delta, falling))

    def test_trend_does_not_change_score_or_level(self):
        data = {"drain_id": "D-001", "blockage_percentage": 70, "rainfall": 100}
        plain = assess_with_history(data)
        for _ in range(3):
            r = assess_with_trend(data)
            for key in ("flood_risk_score", "risk_level", "recommendation", "risk_factors", "warnings", "inputs"):
                self.assertEqual(r[key], plain[key])

    def test_drains_are_isolated(self):
        assess_with_trend({"drain_id": "D-001", "blockage_percentage": 90, "rainfall": 150})
        r = assess_with_trend({"drain_id": "D-002", "blockage_percentage": 10, "rainfall": 1})
        self.assertEqual(r["trend"]["direction"], "NEW")

    def test_invalid_assessment_is_unknown_and_not_logged(self):
        r = assess_with_trend({"drain_id": "D-017", "blockage_percentage": 150})
        self.assertEqual(r["status"], "ERROR")
        self.assertEqual(r["trend"], {"direction": "UNKNOWN", "change": None, "previous_score": None})
        self.assertNotIn("D-017", trend._LOG)
        r = assess_with_trend({"drain_id": "D-017", "blockage_percentage": 50, "rainfall": 10})
        self.assertEqual(r["trend"]["direction"], "NEW")

    def test_no_drain_id_is_unknown_and_not_logged(self):
        r = assess_with_trend({"blockage_percentage": 50, "rainfall": 10})
        self.assertEqual(r["trend"]["direction"], "UNKNOWN")
        self.assertEqual(len(trend._LOG), 0)

    def test_log_is_bounded(self):
        for i in range(trend.MAX_DRAINS + 25):
            assess_with_trend({"drain_id": f"T-{i}", "blockage_percentage": 50, "rainfall": 10})
        self.assertEqual(len(trend._LOG), trend.MAX_DRAINS)
        for _ in range(trend.MAX_READINGS_PER_DRAIN + 10):
            assess_with_trend({"drain_id": "T-last", "blockage_percentage": 50, "rainfall": 10})
        self.assertEqual(len(trend._LOG["T-last"]), trend.MAX_READINGS_PER_DRAIN)


if __name__ == "__main__":
    unittest.main()
