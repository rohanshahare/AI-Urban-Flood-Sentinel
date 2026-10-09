import unittest
from unittest.mock import patch

from risk_engine import engine
from risk_engine.engine import assess_flood_risk as run
from risk_engine.normalise import normalize_rainfall


def warned(result, text):
    return any(text.lower() in w.lower() for w in result["warnings"])


class ScoreTests(unittest.TestCase):
    def test_reference_cases(self):
        r = run({"drain_id": "A", "blockage_percentage": 15, "rainfall": 10, "history": "LOW"})
        self.assertEqual((r["flood_risk_score"], r["risk_level"]), (20, "LOW"))

        # 52 is above the 50 MODERATE limit, so it must be HIGH.
        r = run({"drain_id": "B", "blockage_percentage": 50, "rainfall": 40, "history": "MEDIUM"})
        self.assertEqual((r["flood_risk_score"], r["risk_level"]), (52, "HIGH"))

        r = run({"drain_id": "C", "blockage_percentage": 90, "rainfall": 150, "history": "HIGH"})
        self.assertEqual((r["flood_risk_score"], r["risk_level"]), (94, "CRITICAL"))

    def test_missing_history_renormalises_and_warns(self):
        r = run({"blockage_percentage": 82, "rainfall": "Heavy"})
        self.assertEqual((r["flood_risk_score"], r["risk_level"]), (81, "CRITICAL"))
        self.assertTrue(warned(r, "Historical data unavailable"))
        self.assertIsNone(r["inputs"]["history_category"])

    def test_level_boundaries(self):
        cases = {0: "LOW", 25: "LOW", 26: "MODERATE", 50: "MODERATE", 51: "HIGH",
                 75: "HIGH", 76: "CRITICAL", 100: "CRITICAL"}
        for score, level in cases.items():
            self.assertEqual(next(n for limit, n in engine.LEVELS if score <= limit), level)

    def test_extremes(self):
        low = run({"blockage_percentage": 0, "rainfall": 0, "history": "LOW"})
        high = run({"blockage_percentage": 100, "rainfall": 300, "history": "HIGH"})
        self.assertEqual(low["risk_level"], "LOW")
        self.assertEqual((high["flood_risk_score"], high["risk_level"]), (98, "CRITICAL"))

    def test_recommendation_matches_level(self):
        for b in (0, 40, 60, 100):
            r = run({"blockage_percentage": b, "rainfall": 20, "history": "MEDIUM"})
            self.assertEqual(r["recommendation"], engine.RECOMMENDATIONS[r["risk_level"]])


class BlockageValidationTests(unittest.TestCase):
    def test_invalid_blockage_is_error_without_score(self):
        for bad in (150, -1, "abc", None, True, float("nan"), float("inf")):
            with self.subTest(bad=bad):
                r = run({"drain_id": "F", "blockage_percentage": bad, "rainfall": 50, "history": "HIGH"})
                self.assertEqual(r["status"], "ERROR")
                self.assertIsNone(r["flood_risk_score"])
                self.assertIsNone(r["risk_level"])

    def test_missing_blockage_key_is_error(self):
        self.assertEqual(run({"drain_id": "F", "rainfall": 50})["status"], "ERROR")


class RainfallTests(unittest.TestCase):
    def test_band_edges(self):
        edges = {0: "NONE", 2.4: "NONE", 2.5: "LIGHT", 15.5: "LIGHT", 15.6: "MODERATE",
                 64.4: "MODERATE", 64.5: "HEAVY", 115.5: "HEAVY", 115.6: "VERY_HEAVY",
                 204.4: "VERY_HEAVY", 204.5: "EXTREMELY_HEAVY", 1000: "EXTREMELY_HEAVY"}
        for mm, category in edges.items():
            self.assertEqual(normalize_rainfall(mm)[0], category, mm)

    def test_category_strings(self):
        self.assertEqual(normalize_rainfall(" very heavy ")[0], "VERY_HEAVY")
        self.assertEqual(normalize_rainfall("Heavy")[0], "HEAVY")

    def test_missing_rainfall_is_labelled_missing(self):
        r = run({"blockage_percentage": 82, "history": "HIGH"})
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["inputs"]["rainfall_source"], "ASSUMED_MISSING")
        self.assertEqual(r["inputs"]["rainfall_category"], "MODERATE")
        self.assertTrue(warned(r, "not provided"))
        self.assertFalse(warned(r, "invalid rainfall"))

    def test_invalid_rainfall_is_labelled_invalid(self):
        for bad in (-5, float("nan"), float("inf"), "monsoon", True, [3]):
            with self.subTest(bad=bad):
                r = run({"blockage_percentage": 82, "rainfall": bad, "history": "HIGH"})
                self.assertEqual(r["inputs"]["rainfall_source"], "ASSUMED_INVALID")
                self.assertTrue(warned(r, "invalid rainfall"))
                self.assertFalse(warned(r, "not provided"))

    def test_provided_rainfall_is_labelled_provided(self):
        r = run({"blockage_percentage": 50, "rainfall": 90, "history": "LOW"})
        self.assertEqual(r["inputs"]["rainfall_source"], "PROVIDED")
        self.assertEqual(r["inputs"]["rainfall_category"], "HEAVY")


class WarningTests(unittest.TestCase):
    def test_low_and_invalid_confidence(self):
        r = run({"blockage_percentage": 60, "rainfall": 30, "confidence": 0.3})
        self.assertTrue(warned(r, "manual verification"))
        r = run({"blockage_percentage": 60, "rainfall": 30, "confidence": 7})
        self.assertTrue(warned(r, "invalid confidence"))

    def test_invalid_history_ignored_with_warning(self):
        r = run({"blockage_percentage": 60, "rainfall": 30, "history": "EXTREME"})
        self.assertTrue(warned(r, "invalid history"))
        self.assertIsNone(r["inputs"]["history_category"])

    def test_synthetic_label(self):
        r = run({"blockage_percentage": 60, "rainfall": 30, "data_source": "SYNTHETIC"})
        self.assertTrue(warned(r, "SYNTHETIC"))
        self.assertTrue(r["inputs"]["synthetic_data"])


class SafetyFloorTests(unittest.TestCase):
    def test_floor_never_fires_with_current_config(self):
        # Documents why the floor is only a guard: the lowest score with
        # blockage >= 70 and rain >= HEAVY is already HIGH.
        for b in range(70, 101):
            for rain in ("HEAVY", "VERY_HEAVY", "EXTREMELY_HEAVY"):
                for hist in (None, "LOW", "MEDIUM", "HIGH"):
                    r = run({"blockage_percentage": b, "rainfall": rain, "history": hist})
                    self.assertGreaterEqual(r["flood_risk_score"], 66)
                    self.assertFalse(warned(r, "safety rule"))

    def test_floor_fires_if_weights_are_retuned(self):
        weights = {"blockage": 0.1, "rainfall": 0.1, "history": 0.8}
        with patch.object(engine, "WEIGHTS", weights):
            r = run({"blockage_percentage": 80, "rainfall": "HEAVY", "history": "LOW"})
        self.assertEqual(r["risk_level"], "HIGH")
        self.assertTrue(warned(r, "safety rule"))


if __name__ == "__main__":
    unittest.main()
