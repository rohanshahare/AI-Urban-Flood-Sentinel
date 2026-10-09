"""Backend tests. Ollama is stubbed; the vision, pipeline and risk code are real."""
import unittest
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
except ImportError:  # backend deps not installed in this interpreter
    raise unittest.SkipTest("fastapi/httpx not installed; see requirements.txt")

from backend import main, pipeline
from risk_engine.history import assess_with_history
from risk_engine.trend import reset_log
from vision import VisionServiceError

PNG = b"\x89PNG\r\n\x1a\n" + b"test-image-payload"
TOP_KEYS = {"processing_status", "vision", "risk", "rainfall", "alert", "drain", "error"}
VISION_KEYS = set(pipeline.VISION_FIELDS)
RISK_KEYS = {"flood_risk_score", "risk_level", "risk_factors", "recommendation", "warnings", "trend", "inputs"}
ALERT_KEYS = {"triggered", "level", "title", "message", "recommendation"}
DRAIN_KEYS = {"drain_id", "lat", "lon", "processing_status", "risk_level", "flood_risk_score", "blockage_percentage", "synthetic"}


def model_result(**overrides):
    result = {
        "drain_visible": True, "image_quality": "good", "blockage_detected": True,
        "blockage_percentage": 70, "assessment_uncertain": False,
        "observations": "Debris covers the opening.", "warnings": ["model warning"],
    }
    result.update(overrides)
    return result


UNCERTAIN = model_result(
    drain_visible=False, blockage_detected=False, blockage_percentage=None,
    assessment_uncertain=True, image_quality="poor", warnings=["Drain not visible."],
)


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        reset_log()
        main._UPLOADED.clear()
        self.client = TestClient(main.app, raise_server_exceptions=False)

    def post(self, data=None, content=PNG, files=True):
        kwargs = {"files": {"image": ("drain.png", content, "image/png")}} if files else {}
        return self.client.post("/analyze", data=data or {}, **kwargs)

    def stub(self, **overrides):
        return patch("vision.drain_analysis._call_ollama", return_value=model_result(**overrides))

    def assert_envelope(self, body):
        self.assertEqual(set(body), TOP_KEYS)
        self.assertEqual(set(body["vision"]), VISION_KEYS)
        self.assertEqual(set(body["risk"]), RISK_KEYS)
        self.assertEqual(set(body["risk"]["trend"]), {"direction", "change", "previous_score"})
        self.assertEqual(set(body["alert"]), ALERT_KEYS)
        self.assertEqual(set(body["drain"]), DRAIN_KEYS)
        self.assertIn(body["processing_status"], {"completed", "inconclusive", "error"})
        self.assertEqual(body["drain"]["processing_status"], body["processing_status"])


class HealthAndRoutes(ApiTestCase):
    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual((r.status_code, r.json()), (200, {"status": "ok"}))

    def test_unknown_route_uses_error_envelope(self):
        r = self.client.get("/nope")
        self.assertEqual(r.status_code, 404)
        self.assert_envelope(r.json())
        self.assertEqual(r.json()["error"]["code"], "NOT_FOUND")

    def test_dashboard_is_served_and_repo_internals_are_not(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/.git/config").status_code, 404)


class Completed(ApiTestCase):
    def test_completed_uses_real_engine(self):
        with self.stub(blockage_percentage=70):
            r = self.post({"drain_id": "D-017", "rainfall_mm": "90", "lat": "12.97", "lon": "77.59"})
        body = r.json()
        self.assertEqual(r.status_code, 200)
        self.assert_envelope(body)
        self.assertEqual(body["processing_status"], "completed")
        expected = assess_with_history({"drain_id": "D-017", "blockage_percentage": 70.0, "rainfall": 90})
        self.assertEqual(body["risk"]["flood_risk_score"], expected["flood_risk_score"])
        self.assertEqual(body["risk"]["risk_level"], expected["risk_level"])
        self.assertEqual(body["risk"]["recommendation"], expected["recommendation"])
        self.assertEqual(body["risk"]["trend"]["direction"], "NEW")
        self.assertEqual(body["rainfall"], {"mm_per_day": 90.0, "category": "HEAVY", "source": "REQUEST"})
        self.assertEqual(body["vision"]["blockage_percentage"], 70.0)
        self.assertTrue(body["vision"]["blockage_detected"])
        self.assertIn("model warning", body["vision"]["warnings"])
        self.assertTrue(any("SYNTHETIC" in w for w in body["risk"]["warnings"]))
        self.assertEqual(body["drain"]["lat"], 12.97)
        self.assertEqual(body["alert"]["triggered"], body["risk"]["risk_level"] in ("HIGH", "CRITICAL"))
        self.assertIsNone(body["error"])

    def test_results_are_not_hardcoded(self):
        scores = set()
        for pct in (5, 40, 95):
            with self.stub(blockage_percentage=pct):
                scores.add(self.post({"rainfall_mm": "30"}).json()["risk"]["flood_risk_score"])
        self.assertEqual(len(scores), 3)

    def test_missing_rainfall_is_labelled_assumed(self):
        with self.stub():
            body = self.post().json()
        self.assertEqual(body["processing_status"], "completed")
        self.assertEqual(body["rainfall"]["source"], "ASSUMED_DEFAULT")
        self.assertIsNone(body["rainfall"]["mm_per_day"])
        self.assertTrue(any("not provided" in w for w in body["risk"]["warnings"]))

    def test_repeated_analysis_reports_trend_without_changing_score(self):
        with self.stub(blockage_percentage=60):
            first = self.post({"drain_id": "D-002", "rainfall_mm": "5"}).json()
        with self.stub(blockage_percentage=60):
            second = self.post({"drain_id": "D-002", "rainfall_mm": "5"}).json()
        with self.stub(blockage_percentage=95):
            third = self.post({"drain_id": "D-002", "rainfall_mm": "150"}).json()
        self.assertEqual(first["risk"]["trend"]["direction"], "NEW")
        self.assertEqual(second["risk"]["trend"]["direction"], "STABLE")
        self.assertEqual(second["risk"]["flood_risk_score"], first["risk"]["flood_risk_score"])
        self.assertEqual(third["risk"]["trend"]["direction"], "RISING")
        self.assertEqual(third["risk"]["trend"]["previous_score"], second["risk"]["flood_risk_score"])

    def test_without_drain_id_trend_is_unknown(self):
        with self.stub():
            self.assertEqual(self.post().json()["risk"]["trend"]["direction"], "UNKNOWN")


class Inconclusive(ApiTestCase):
    def check(self, body):
        self.assert_envelope(body)
        self.assertEqual(body["processing_status"], "inconclusive")
        self.assertIsNone(body["vision"]["blockage_detected"])
        self.assertIsNone(body["vision"]["blockage_percentage"])
        self.assertIsNone(body["risk"]["flood_risk_score"])
        self.assertIsNone(body["risk"]["risk_level"])
        self.assertIn("Manual inspection", body["risk"]["recommendation"])
        self.assertFalse(body["alert"]["triggered"])
        self.assertIsNone(body["alert"]["level"])
        self.assertIsNone(body["drain"]["risk_level"])
        self.assertIsNone(body["error"])

    def test_uncertain_assessment_skips_scoring(self):
        with patch("vision.drain_analysis._call_ollama", return_value=UNCERTAIN), \
                patch.object(pipeline, "assess_with_trend") as scorer:
            r = self.post({"drain_id": "D-005", "rainfall_mm": "100"})
        scorer.assert_not_called()
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.check(body)
        self.assertIn("Drain not visible.", body["vision"]["warnings"])
        self.assertTrue(any("uncertain" in w.lower() for w in body["vision"]["warnings"]))
        self.assertEqual(body["rainfall"], {"mm_per_day": 100.0, "category": None, "source": "REQUEST"})

    def test_certain_negative_is_also_inconclusive_not_clear(self):
        # Vision returns a null percentage for a clear drain too; never show it as clear.
        with self.stub(blockage_detected=False, blockage_percentage=None):
            self.check(self.post().json())

    def test_inconclusive_does_not_create_trend_entry(self):
        with patch("vision.drain_analysis._call_ollama", return_value=UNCERTAIN):
            self.post({"drain_id": "D-002"})
        with self.stub(blockage_percentage=50):
            body = self.post({"drain_id": "D-002", "rainfall_mm": "5"}).json()
        self.assertEqual(body["risk"]["trend"]["direction"], "NEW")


class Errors(ApiTestCase):
    def check(self, response, status, code):
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assert_envelope(body)
        self.assertEqual(body["processing_status"], "error")
        self.assertEqual(body["error"]["code"], code)
        self.assertTrue(body["error"]["message"])
        self.assertIsNone(body["risk"]["risk_level"])
        self.assertIsNone(body["vision"]["blockage_detected"])
        self.assertFalse(body["alert"]["triggered"])
        self.assertNotIn("Traceback", response.text)
        return body

    def test_invalid_image(self):
        self.check(self.post(content=b"not an image"), 400, "INVALID_INPUT")

    def test_empty_image(self):
        self.check(self.post(content=b""), 400, "INVALID_INPUT")

    def test_missing_image_field(self):
        self.check(self.post({"drain_id": "D-1"}, files=False), 422, "INVALID_REQUEST")

    def test_oversized_image(self):
        with patch.object(main, "MAX_IMAGE_BYTES", 10):
            self.check(self.post(content=PNG), 413, "IMAGE_TOO_LARGE")

    def test_bad_metadata(self):
        bad = [
            {"lat": "12.9"}, {"lon": "77.5"}, {"lat": "91", "lon": "0"}, {"lat": "0", "lon": "181"},
            {"lat": "nan", "lon": "0"}, {"lat": "abc", "lon": "0"},
            {"rainfall_mm": "-1"}, {"rainfall_mm": "abc"}, {"rainfall_mm": "inf"},
            {"drain_id": "has space"}, {"drain_id": "x" * 65},
        ]
        for data in bad:
            with self.subTest(data=data), patch("vision.drain_analysis._call_ollama") as model:
                self.check(self.post(data), 400, "INVALID_INPUT")
                model.assert_not_called()

    def test_ollama_unreachable_is_error_not_clear(self):
        with patch.object(main, "OLLAMA_URL", "http://127.0.0.1:9"), patch.object(main, "VISION_TIMEOUT", 3):
            r = self.post({"drain_id": "D-1"})
        body = self.check(r, 502, "VISION_SERVICE_ERROR")
        self.assertNotIn("127.0.0.1", r.text)
        self.assertNotEqual(body["processing_status"], "completed")

    def test_unusable_model_response(self):
        with patch("vision.drain_analysis._call_ollama", side_effect=VisionServiceError("bad json at http://secret:1")):
            r = self.post()
        self.check(r, 502, "VISION_SERVICE_ERROR")
        self.assertNotIn("secret", r.text)

    def test_risk_engine_failure(self):
        with self.stub(), patch.object(pipeline, "assess_with_trend", return_value={"status": "ERROR", "warnings": ["boom"]}):
            self.check(self.post(), 500, "RISK_ENGINE_ERROR")

    def test_unexpected_exception_is_generic_json(self):
        with patch.object(main, "analyze_drain", side_effect=RuntimeError("secret internals")):
            r = self.post()
        self.check(r, 500, "INTERNAL_ERROR")
        self.assertNotIn("secret", r.text)


class Drains(ApiTestCase):
    def test_schema_and_labels(self):
        r = self.client.get("/drains")
        items = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(5 <= len(items) <= 8)
        for item in items:
            self.assertEqual(set(item), DRAIN_KEYS)
            self.assertTrue(item["synthetic"])
            if item["processing_status"] == "completed":
                self.assertIn(item["risk_level"], {"LOW", "MODERATE", "HIGH", "CRITICAL"})
                self.assertIsInstance(item["flood_risk_score"], int)
            else:
                self.assertEqual(item["processing_status"], "inconclusive")
                self.assertIsNone(item["risk_level"])
                self.assertIsNone(item["flood_risk_score"])

    def test_missing_coordinates_stay_null(self):
        items = {i["drain_id"]: i for i in self.client.get("/drains").json()}
        self.assertIsNone(items["D-010"]["lat"])
        self.assertIsNone(items["D-010"]["lon"])

    def test_listing_does_not_touch_trend_log(self):
        self.client.get("/drains")
        with self.stub(blockage_percentage=50):
            body = self.post({"drain_id": "D-017", "rainfall_mm": "5"}).json()
        self.assertEqual(body["risk"]["trend"]["direction"], "NEW")

    def test_analysed_drain_appears_unlabelled_as_synthetic(self):
        with self.stub(blockage_percentage=88):
            self.post({"drain_id": "UP-1", "lat": "13.0", "lon": "77.6", "rainfall_mm": "120"})
        item = next(i for i in self.client.get("/drains").json() if i["drain_id"] == "UP-1")
        self.assertFalse(item["synthetic"])
        self.assertEqual((item["lat"], item["lon"]), (13.0, 77.6))
        self.assertEqual(item["processing_status"], "completed")


if __name__ == "__main__":
    unittest.main()
