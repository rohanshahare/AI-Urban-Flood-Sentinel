"""Evaluation-script arithmetic, on hand-made rows (these are test inputs, not model results)."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("evaluate_vision", ROOT / "scripts" / "evaluate_vision.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def row(label, prediction, true_pct=None, pred_pct=None):
    return {"label": label, "prediction": prediction, "true_pct": true_pct, "pred_pct": pred_pct}


class EvaluateVision(unittest.TestCase):
    def test_predicted_class_uses_the_vision_contract(self):
        self.assertEqual(ev.predicted_class({"blockage_percentage": 40.0, "warnings": []}), "blocked")
        self.assertEqual(ev.predicted_class({"blockage_percentage": None, "warnings": []}), "not_blocked")
        uncertain = "Assessment is uncertain ...; do not interpret a negative result as proof that the drain is clear."
        self.assertEqual(ev.predicted_class({"blockage_percentage": None, "warnings": [uncertain]}), "inconclusive")

    def test_marker_matches_the_vision_module_text(self):
        source = (ROOT / "vision" / "drain_analysis.py").read_text(encoding="utf-8")
        self.assertIn(ev.UNCERTAIN_MARKER, source)

    def test_summary_counts_inconclusive_separately(self):
        rows = [row("blocked", "blocked", 60, 70), row("blocked", "blocked", 80, 75), row("blocked", "not_blocked"),
                row("blocked", "inconclusive"), row("clear", "not_blocked"), row("clear", "blocked", None, 30),
                row("clear", "inconclusive"), row("clear", "error")]
        s = ev.summarize(rows)
        self.assertEqual(s["n_images"], 8)
        self.assertEqual(s["confusion"]["blocked"], {"blocked": 2, "not_blocked": 1, "inconclusive": 1, "error": 0})
        self.assertEqual(s["coverage"], 0.625)          # 5 decided of 8
        self.assertEqual(s["precision_blocked"], 0.667)  # 2 / (2 + 1)
        self.assertEqual(s["recall_blocked"], 0.667)     # 2 / (2 + 1)
        self.assertEqual(s["false_clear_rate"], 0.333)
        self.assertEqual((s["percentage_mae"], s["percentage_mae_n"]), (7.5, 2))
        self.assertIn("too few", s["caveat"])

    def test_empty_denominators_are_none_not_zero(self):
        s = ev.summarize([row("clear", "inconclusive")])
        self.assertIsNone(s["precision_blocked"])
        self.assertIsNone(s["recall_blocked"])
        self.assertIsNone(s["percentage_mae"])

    def test_manifest_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "m.csv"
            good.write_text("image,label,blockage_percentage\na.jpg,Blocked,60\nb.jpg,clear,\n", encoding="utf-8")
            rows = ev.read_manifest(good)
            self.assertEqual([(r["label"], r["true_pct"]) for r in rows], [("blocked", 60.0), ("clear", None)])
            bad = Path(tmp) / "bad.csv"
            bad.write_text("image,label\na.jpg,maybe\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                ev.read_manifest(bad)


if __name__ == "__main__":
    unittest.main()
