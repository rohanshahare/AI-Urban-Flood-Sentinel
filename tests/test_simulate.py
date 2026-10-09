"""What-if simulator and drain-detail endpoints."""
import unittest
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient  # noqa: F401
except ImportError:
    raise unittest.SkipTest("fastapi/httpx not installed; see requirements.txt")

from backend import main
from risk_engine import trend, what_if
from risk_engine.history import assess_with_history
from tests import test_api as base


def payload(b0=50, r0=5, b1=90, r1=150, drain_id="D-002"):
    return {"drain_id": drain_id, "baseline": {"blockage_percentage": b0, "rainfall_mm": r0},
            "scenario": {"blockage_percentage": b1, "rainfall_mm": r1}}


class Simulate(base.ApiTestCase):
    def sim(self, body):
        return self.client.post("/simulate", json=body)

    def test_reuses_the_existing_scoring_logic(self):
        with patch.object(what_if, "assess_with_history", wraps=assess_with_history) as scorer:
            r = self.sim(payload())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(scorer.call_count, 2)  # baseline + scenario, through the real engine entry point
        expected_base = assess_with_history({"drain_id": "D-002", "blockage_percentage": 50.0, "rainfall": 5.0})
        expected_hypo = assess_with_history({"drain_id": "D-002", "blockage_percentage": 90.0, "rainfall": 150.0})
        body = r.json()
        self.assertEqual(body["baseline"]["flood_risk_score"], expected_base["flood_risk_score"])
        self.assertEqual(body["scenario"]["flood_risk_score"], expected_hypo["flood_risk_score"])
        self.assertEqual(body["scenario"]["risk_level"], expected_hypo["risk_level"])

    def test_response_is_labelled_hypothetical_and_has_no_alert(self):
        body = self.sim(payload()).json()
        self.assertIs(body["simulation"], True)
        self.assertIn("HYPOTHETICAL", body["label"])
        self.assertIn("not a prediction", body["label"])
        self.assertNotIn("alert", body)
        self.assertNotIn("processing_status", body)

    def test_change_summary(self):
        body = self.sim(payload(b0=50, r0=5, b1=90, r1=150)).json()
        change = body["change"]
        self.assertEqual(change["score_delta"], body["scenario"]["flood_risk_score"] - body["baseline"]["flood_risk_score"])
        self.assertEqual((change["level_from"], change["level_to"]), (body["baseline"]["risk_level"], body["scenario"]["risk_level"]))
        self.assertIs(change["level_changed"], change["level_from"] != change["level_to"])
        self.assertEqual({c["input"] for c in change["changed_inputs"]}, {"blockage_percentage", "rainfall"})

    def test_unchanged_scenario_reports_no_change(self):
        body = self.sim(payload(b0=60, r0=40, b1=60, r1=40)).json()
        self.assertEqual(body["change"]["score_delta"], 0)
        self.assertEqual(body["change"]["changed_inputs"], [])
        self.assertIs(body["change"]["level_changed"], False)

    def test_null_baseline_rainfall_is_assumed_and_labelled(self):
        body = self.sim({"baseline": {"blockage_percentage": 40, "rainfall_mm": None},
                         "scenario": {"blockage_percentage": 40, "rainfall_mm": 100}}).json()
        self.assertEqual(body["baseline"]["inputs"]["rainfall_source"], "ASSUMED_MISSING")
        self.assertEqual(body["scenario"]["inputs"]["rainfall_source"], "PROVIDED")
        self.assertEqual(body["change"]["changed_inputs"][0]["from"], None)

    def test_never_touches_trend_history_or_stored_results(self):
        with self.stub(blockage_percentage=60):
            self.post({"drain_id": "D-002", "rainfall_mm": "5"})
        log_before = {k: list(v) for k, v in trend._LOG.items()}
        stored_before = dict(main._UPLOADED)
        for _ in range(3):
            self.sim(payload(b0=60, r0=5, b1=100, r1=250))
        self.assertEqual({k: list(v) for k, v in trend._LOG.items()}, log_before)
        self.assertEqual(main._UPLOADED, stored_before)
        with self.stub(blockage_percentage=60):
            self.assertEqual(self.post({"drain_id": "D-002", "rainfall_mm": "5"}).json()["risk"]["trend"]["direction"], "STABLE")

    def test_baseline_matches_the_real_analysis(self):
        with self.stub(blockage_percentage=70):
            analysed = self.post({"drain_id": "D-017", "rainfall_mm": "90"}).json()
        sim = self.sim({"drain_id": "D-017", "baseline": {"blockage_percentage": 70, "rainfall_mm": 90},
                        "scenario": {"blockage_percentage": 30, "rainfall_mm": 90}}).json()
        self.assertEqual(sim["baseline"]["flood_risk_score"], analysed["risk"]["flood_risk_score"])
        self.assertEqual(sim["baseline"]["risk_level"], analysed["risk"]["risk_level"])
        self.assertLess(sim["change"]["score_delta"], 0)

    def test_invalid_inputs_are_rejected_with_the_error_envelope(self):
        def case(**over):
            body = payload()
            for path, value in over.items():
                side, key = path.split("__")
                body[side][key] = value
            return body

        bad = [
            case(baseline__blockage_percentage=101), case(scenario__blockage_percentage=-1),
            case(scenario__blockage_percentage="50"), case(scenario__blockage_percentage=True),
            case(scenario__blockage_percentage=None), case(scenario__rainfall_mm=-5),
            case(baseline__rainfall_mm="heavy"), case(baseline__rainfall_mm=False),
            {"baseline": payload()["baseline"]}, {"scenario": payload()["scenario"]}, {},
            {"baseline": [], "scenario": {}}, [], "text", {**payload(), "drain_id": "bad id!"},
        ]
        for body in bad:
            with self.subTest(body=body):
                r = self.sim(body)
                self.assertEqual(r.status_code, 400)
                self.assert_envelope(r.json())
                self.assertEqual(r.json()["error"]["code"], "INVALID_INPUT")

    def test_non_finite_numbers_and_bad_json(self):
        for raw in (b'{"baseline":{"blockage_percentage":NaN},"scenario":{"blockage_percentage":5}}',
                    b'{"baseline":{"blockage_percentage":1},"scenario":{"blockage_percentage":Infinity}}',
                    b"not json", b""):
            r = self.client.post("/simulate", content=raw, headers={"Content-Type": "application/json"})
            self.assertEqual(r.status_code, 400, raw)
            self.assertEqual(r.json()["error"]["code"], "INVALID_INPUT")

    def test_engine_error_does_not_leak(self):
        with patch.object(what_if, "assess_with_history", return_value={"status": "ERROR", "warnings": ["secret detail"]}):
            r = self.sim(payload())
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("secret", r.text)


class DrainDetail(base.ApiTestCase):
    def test_demo_detail_is_labelled_synthetic_and_never_alerts(self):
        r = self.client.get("/drains/D-001")
        body = r.json()
        self.assertEqual(r.status_code, 200)
        self.assert_envelope(body)
        self.assertEqual(body["processing_status"], "completed")
        self.assertEqual(body["risk"]["risk_level"], "CRITICAL")
        self.assertTrue(body["drain"]["synthetic"])
        self.assertIn("Synthetic demo record", body["vision"]["warnings"][0])
        self.assertEqual(body["rainfall"]["source"], "SYNTHETIC_DEMO")
        self.assertIsNone(body["vision"]["blockage_detected"])
        self.assertFalse(body["alert"]["triggered"])
        self.assertEqual(body["risk"]["trend"]["direction"], "UNKNOWN")

    def test_detail_agrees_with_the_list_for_every_demo_drain(self):
        for item in self.client.get("/drains").json():
            detail = self.client.get(f"/drains/{item['drain_id']}").json()
            with self.subTest(drain=item["drain_id"]):
                self.assertEqual(detail["processing_status"], item["processing_status"])
                self.assertEqual(detail["risk"]["risk_level"], item["risk_level"])
                self.assertEqual(detail["risk"]["flood_risk_score"], item["flood_risk_score"])
                self.assertEqual(detail["vision"]["blockage_percentage"], item["blockage_percentage"])
                self.assertEqual((detail["drain"]["lat"], detail["drain"]["lon"]), (item["lat"], item["lon"]))

    def test_inconclusive_demo_drain_has_no_score_or_alert(self):
        body = self.client.get("/drains/D-005").json()
        self.assertEqual(body["processing_status"], "inconclusive")
        self.assertIsNone(body["risk"]["flood_risk_score"])
        self.assertFalse(body["alert"]["triggered"])
        self.assertIn("Manual inspection", body["risk"]["recommendation"])

    def test_listing_and_detail_do_not_write_trend_history(self):
        self.client.get("/drains")
        self.client.get("/drains/D-017")
        self.assertEqual(len(trend._LOG), 0)

    def test_records_say_what_each_level_rests_on(self):
        with self.stub(blockage_percentage=70):
            self.post({"drain_id": "D-017"})                      # no rainfall, synthetic history
            self.post({"drain_id": "X-1", "rainfall_mm": "40"})  # supplied rainfall, no history
        with patch("vision.drain_analysis._call_ollama", return_value=base.UNCERTAIN):
            self.post({"drain_id": "X-2"})
        items = {i["drain_id"]: i for i in self.client.get("/drains").json()}
        self.assertEqual((items["D-017"]["rainfall_source"], items["D-017"]["synthetic_history"]), ("ASSUMED_DEFAULT", True))
        self.assertEqual((items["X-1"]["rainfall_source"], items["X-1"]["synthetic_history"]), ("REQUEST", False))
        self.assertEqual(items["X-1"]["recommendation"], self.client.get("/drains/X-1").json()["risk"]["recommendation"])
        self.assertEqual((items["X-2"]["rainfall_source"], items["X-2"]["synthetic_history"]), (None, None))
        self.assertIn("Manual inspection", items["X-2"]["recommendation"])
        self.assertEqual((items["D-001"]["rainfall_source"], items["D-001"]["synthetic_history"]), ("SYNTHETIC_DEMO", True))

    def test_unknown_drain_is_404_envelope(self):
        r = self.client.get("/drains/NOPE")
        self.assertEqual(r.status_code, 404)
        self.assert_envelope(r.json())

    def test_analysed_drain_returns_the_stored_analysis(self):
        with self.stub(blockage_percentage=88):
            posted = self.post({"drain_id": "UP-9", "lat": "13", "lon": "77.6", "rainfall_mm": "120"}).json()
        stored = self.client.get("/drains/UP-9").json()
        self.assertEqual(stored, posted)
        self.assertFalse(stored["drain"]["synthetic"])


if __name__ == "__main__":
    unittest.main()
