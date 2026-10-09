import unittest

from risk_engine.history import _HISTORY, assess_with_history, vulnerability_label


class HistoryTests(unittest.TestCase):
    def test_vulnerability_label(self):
        self.assertEqual(vulnerability_label(3, 6, True), "HIGH")
        self.assertEqual(vulnerability_label(0, 0, False), "LOW")
        self.assertEqual(vulnerability_label(1, 0, True), "MEDIUM")
        self.assertEqual(vulnerability_label(0, 4, False), "LOW")

    def test_every_loaded_record_is_synthetic(self):
        self.assertTrue(_HISTORY)
        self.assertTrue(all(r["data_source"] == "SYNTHETIC" for r in _HISTORY.values()))

    def test_known_drain_uses_synthetic_history(self):
        r = assess_with_history({"drain_id": "D-017", "blockage_percentage": 82, "rainfall": 80})
        self.assertEqual(r["risk_level"], "CRITICAL")
        self.assertEqual(r["inputs"]["history_category"], "HIGH")
        self.assertTrue(r["inputs"]["synthetic_data"])
        self.assertTrue(any("SYNTHETIC" in w for w in r["warnings"]))

    def test_unknown_drain_falls_back_with_warning(self):
        r = assess_with_history({"drain_id": "D-999", "blockage_percentage": 82, "rainfall": 80})
        self.assertEqual(r["status"], "OK")
        self.assertIsNone(r["inputs"]["history_category"])
        self.assertFalse(r["inputs"]["synthetic_data"])
        self.assertTrue(any("Historical data unavailable" in w for w in r["warnings"]))

    def test_missing_or_unhashable_drain_id_does_not_crash(self):
        for drain_id in (None, ["D-017"], 17):
            r = assess_with_history({"drain_id": drain_id, "blockage_percentage": 50, "rainfall": 10})
            self.assertEqual(r["status"], "OK")

    def test_caller_history_wins_and_input_is_not_mutated(self):
        data = {"drain_id": "D-017", "blockage_percentage": 50, "rainfall": 10, "history": "LOW"}
        before = dict(data)
        r = assess_with_history(data)
        self.assertEqual(r["inputs"]["history_category"], "LOW")
        self.assertEqual(data, before)


if __name__ == "__main__":
    unittest.main()
