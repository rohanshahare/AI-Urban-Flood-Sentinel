import math
import unittest
from fractions import Fraction
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



class FormulaTests(unittest.TestCase):
    RAIN = {"NONE": Fraction(0), "LIGHT": Fraction(1, 5), "MODERATE": Fraction(1, 2),
            "HEAVY": Fraction(4, 5), "VERY_HEAVY": Fraction(1), "EXTREMELY_HEAVY": Fraction(1)}
    HIST = {None: None, "LOW": Fraction(3, 10), "MEDIUM": Fraction(3, 5), "HIGH": Fraction(9, 10)}

    def test_weights_are_45_35_20(self):
        self.assertEqual(engine.WEIGHTS, {"blockage": 0.45, "rainfall": 0.35, "history": 0.20})

    def test_matches_independent_exact_half_up_calculation(self):
        # Independent re-computation with Fractions over the whole input grid, including exact
        # .5 ties (which float arithmetic used to round inconsistently).
        for b in range(101):
            for rain, rv in self.RAIN.items():
                for hist, hv in self.HIST.items():
                    parts = [(Fraction(b, 100), Fraction(45, 100)), (rv, Fraction(35, 100))]
                    if hv is not None:
                        parts.append((hv, Fraction(20, 100)))
                    exact = 100 * sum(v * w for v, w in parts) / sum(w for _, w in parts)
                    got = run({"blockage_percentage": b, "rainfall": rain, "history": hist})["flood_risk_score"]
                    self.assertEqual(got, math.floor(exact + Fraction(1, 2)), (b, rain, hist))

    def test_ties_round_half_up(self):
        # 10% blockage, NONE rain, LOW history is exactly 10.5; 8%/HEAVY/no history is exactly 39.5.
        self.assertEqual(run({"blockage_percentage": 10, "rainfall": "NONE", "history": "LOW"})["flood_risk_score"], 11)
        self.assertEqual(run({"blockage_percentage": 8, "rainfall": "HEAVY"})["flood_risk_score"], 40)

    def test_exact_ties_at_level_boundaries_round_up_consistently(self):
        # These inputs score exactly 25.5, 50.5 and 75.5. The old float code rounded 50.5 down
        # (MODERATE) but 25.5 and 75.5 up; half-up now resolves every boundary tie upward.
        cases = [((30, "NONE", "MEDIUM"), 26, "MODERATE"),
                 ((10, "HEAVY", "HIGH"), 51, "HIGH"),
                 ((50, "VERY_HEAVY", "HIGH"), 76, "CRITICAL")]
        for (b, rain, hist), score, level in cases:
            r = run({"blockage_percentage": b, "rainfall": rain, "history": hist})
            self.assertEqual((r["flood_risk_score"], r["risk_level"]), (score, level), (b, rain, hist))

    def test_small_input_changes_can_cross_a_boundary(self):
        # Documents sensitivity: categories are hard thresholds, so 0.1 percentage point of
        # blockage can change the level near a boundary. The UI shows the score next to the level.
        cases = [((29.9, "NONE", "MEDIUM"), 25, "LOW"), ((30.1, "NONE", "MEDIUM"), 26, "MODERATE"),
                 ((9.9, "HEAVY", "HIGH"), 50, "MODERATE"), ((10.0, "HEAVY", "HIGH"), 51, "HIGH")]
        for (b, rain, hist), score, level in cases:
            r = run({"blockage_percentage": b, "rainfall": rain, "history": hist})
            self.assertEqual((r["flood_risk_score"], r["risk_level"]), (score, level), (b, rain, hist))

    def test_score_is_monotonic_in_blockage_and_rainfall(self):
        for hist in (None, "LOW", "HIGH"):
            prev = -1
            for b in range(101):
                score = run({"blockage_percentage": b, "rainfall": "LIGHT", "history": hist})["flood_risk_score"]
                self.assertGreaterEqual(score, prev)
                prev = score
            prev = -1
            for mm in (0, 2.5, 15.6, 64.5, 115.6, 204.5):
                score = run({"blockage_percentage": 40, "rainfall": mm, "history": hist})["flood_risk_score"]
                self.assertGreaterEqual(score, prev)
                prev = score

    def test_fractional_blockage_is_scored(self):
        self.assertEqual(run({"blockage_percentage": 75.3, "rainfall": "HEAVY", "history": "LOW"})["status"], "OK")


if __name__ == "__main__":
    unittest.main()
