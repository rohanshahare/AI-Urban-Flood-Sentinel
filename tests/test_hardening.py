"""Backend hardening: real HTTP against a fake Ollama and (for concurrency) a live uvicorn server.

The model itself is faked; vision's HTTP client, the pipeline and the risk engine are real.
"""
import json
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

try:
    import httpx
    import uvicorn
except ImportError:
    raise unittest.SkipTest("fastapi/httpx/uvicorn not installed; see requirements.txt")

from backend import main
from tests import test_api as base

GOOD = base.model_result(blockage_percentage=80)


class FakeOllama:
    """Tiny stand-in for Ollama's /api/chat. `mode` selects the behaviour."""

    def __init__(self):
        self.mode, self.delay, self.calls = "ok", 0.0, 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                owner.calls += 1
                time.sleep(owner.delay)
                if owner.mode == "http500":
                    self.send_response(500)
                    self.end_headers()
                    return
                if owner.mode == "bad_envelope":
                    body = b"this is not json"
                elif owner.mode == "bad_content":
                    body = json.dumps({"message": {"content": "not json either"}}).encode()
                elif owner.mode == "missing_fields":
                    body = json.dumps({"message": {"content": json.dumps({"blockage_detected": True})}}).encode()
                else:
                    payload = owner.payload if owner.mode == "custom" else GOOD
                    body = json.dumps({"message": {"content": json.dumps(payload)}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class FakeOllamaCase(base.ApiTestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = FakeOllama()

    @classmethod
    def tearDownClass(cls):
        cls.ollama.close()

    def setUp(self):
        super().setUp()
        self.ollama.mode, self.ollama.delay = "ok", 0.0
        patcher = patch.object(main, "OLLAMA_URL", self.ollama.url)
        patcher.start()
        self.addCleanup(patcher.stop)


class VisionOverRealHttp(FakeOllamaCase):
    def test_success_is_completed(self):
        body = self.post({"drain_id": "D-017", "rainfall_mm": "90"}).json()
        self.assert_envelope(body)
        self.assertEqual(body["processing_status"], "completed")
        self.assertEqual(body["vision"]["blockage_percentage"], 80.0)
        self.assertIsNotNone(body["risk"]["flood_risk_score"])

    def test_uncertain_model_output_is_inconclusive(self):
        self.ollama.mode, self.ollama.payload = "custom", base.UNCERTAIN
        r = self.post()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["processing_status"], "inconclusive")
        self.assertIsNone(r.json()["risk"]["flood_risk_score"])

    def test_unusable_model_responses_are_502_never_clear(self):
        pct_out_of_range = base.model_result(blockage_percentage=140)
        bad_flag = base.model_result(blockage_detected="yes")
        for mode, payload in (("http500", None), ("bad_envelope", None), ("bad_content", None), ("missing_fields", None),
                              ("custom", pct_out_of_range), ("custom", bad_flag)):
            with self.subTest(mode=mode, payload=payload):
                self.ollama.mode, self.ollama.payload = mode, payload
                r = self.post({"drain_id": "D-1"})
                body = r.json()
                self.assertEqual(r.status_code, 502)
                self.assertEqual(body["processing_status"], "error")
                self.assertEqual(body["error"]["code"], "VISION_SERVICE_ERROR")
                self.assertIsNone(body["vision"]["blockage_detected"])
                self.assertIsNone(body["risk"]["risk_level"])
                self.assertNotIn("127.0.0.1", r.text)

    def test_model_timeout_is_502(self):
        self.ollama.delay = 2.0
        with patch.object(main, "VISION_TIMEOUT", 0.5):
            started = time.monotonic()
            r = self.post()
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()["error"]["code"], "VISION_SERVICE_ERROR")

    def test_repeated_requests_stay_consistent(self):
        scores = [self.post({"drain_id": "D-006", "rainfall_mm": "70"}).json()["risk"] for _ in range(4)]
        self.assertEqual({r["flood_risk_score"] for r in scores}, {scores[0]["flood_risk_score"]})
        self.assertEqual([r["trend"]["direction"] for r in scores], ["NEW", "STABLE", "STABLE", "STABLE"])

    def test_invalid_input_never_reaches_the_model(self):
        before = self.ollama.calls
        self.post({"lat": "12"})
        self.post(content=b"%PDF-1.4 not an image")
        self.assertEqual(self.ollama.calls, before)


class UploadValidation(base.ApiTestCase):
    def check_400(self, **kwargs):
        with patch("vision.drain_analysis._call_ollama") as model:
            r = self.post(**kwargs)
            model.assert_not_called()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], "INVALID_INPUT")

    def test_unsupported_content_is_rejected(self):
        for content in (b"%PDF-1.4 fake pdf", b"<svg xmlns='http://www.w3.org/2000/svg'/>", b"plain text file", b"PK\x03\x04zip"):
            with self.subTest(content=content[:8]):
                self.check_400(content=content)

    def test_declared_type_is_not_trusted(self):
        r = self.client.post("/analyze", files={"image": ("evil.png", b"not really a png", "image/png")})
        self.assertEqual(r.status_code, 400)

    def test_content_length_precheck_rejects_before_parsing(self):
        with patch.object(main, "MAX_IMAGE_BYTES", 1000), patch.object(main, "analyze_drain") as vision:
            r = self.post(content=b"\x89PNG\r\n\x1a\n" + b"0" * 200_000)
            vision.assert_not_called()
        self.assertEqual(r.status_code, 413)
        self.assertEqual(r.json()["error"]["code"], "IMAGE_TOO_LARGE")
        self.assertEqual(set(r.json()), base.TOP_KEYS)

    def test_real_limit_is_ten_mib(self):
        self.assertEqual(main.MAX_IMAGE_BYTES, 10 * 1024 * 1024)
        over = b"\x89PNG\r\n\x1a\n" + b"0" * (main.MAX_IMAGE_BYTES + 1)
        self.assertEqual(self.post(content=over).status_code, 413)

    def test_blank_form_fields_are_treated_as_absent(self):
        with self.stub():
            r = self.post({"drain_id": "", "lat": " ", "lon": "", "rainfall_mm": ""})
        self.assertEqual(r.json()["processing_status"], "completed")
        self.assertIsNone(r.json()["drain"]["lat"])

    def test_records_without_coordinates_are_kept_without_inventing_any(self):
        with self.stub():
            self.post({"drain_id": "NOLOC"})
        item = next(i for i in self.client.get("/drains").json() if i["drain_id"] == "NOLOC")
        self.assertIsNone(item["lat"])
        self.assertIsNone(item["lon"])

    def test_uploaded_record_store_is_bounded(self):
        with patch.object(main, "MAX_UPLOADED_DRAINS", 3), self.stub():
            for i in range(6):
                self.post({"drain_id": f"CAP-{i}"})
        self.assertEqual(list(main._UPLOADED), ["CAP-3", "CAP-4", "CAP-5"])

    def test_cors_only_admits_local_origins(self):
        local = self.client.get("/health", headers={"Origin": "http://localhost:5500"})
        remote = self.client.get("/health", headers={"Origin": "https://evil.example"})
        self.assertEqual(local.headers.get("access-control-allow-origin"), "http://localhost:5500")
        self.assertNotIn("access-control-allow-origin", remote.headers)


class LiveServer(unittest.TestCase):
    """A real uvicorn server: proves inference does not block the event loop and assets are served."""

    @classmethod
    def setUpClass(cls):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        cls.url = f"http://127.0.0.1:{port}"
        cls.server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="error"))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        for _ in range(100):
            if cls.server.started:
                break
            time.sleep(0.05)
        cls.ollama = FakeOllama()
        cls.patch = patch.object(main, "OLLAMA_URL", cls.ollama.url)
        cls.patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()
        cls.ollama.close()
        cls.server.should_exit = True
        cls.thread.join(5)

    def test_health_stays_responsive_during_slow_inference(self):
        self.ollama.delay = 1.5
        result = {}

        def analyze():
            result["r"] = httpx.post(f"{self.url}/analyze", files={"image": ("d.png", base.PNG, "image/png")}, timeout=20)

        worker = threading.Thread(target=analyze)
        worker.start()
        time.sleep(0.4)  # the analysis is now blocked inside the fake model
        started = time.monotonic()
        health = httpx.get(f"{self.url}/health", timeout=5)
        elapsed = time.monotonic() - started
        worker.join(20)
        self.ollama.delay = 0
        self.assertEqual(health.status_code, 200)
        self.assertLess(elapsed, 0.8, "event loop was blocked by model inference")
        self.assertEqual(result["r"].json()["processing_status"], "completed")

    def test_documented_endpoints_and_assets(self):
        for path, kind in (("/", "text/html"), ("/health", "application/json"), ("/docs", "text/html"),
                           ("/openapi.json", "application/json"), ("/drains", "application/json"),
                           ("/js/main.js", "javascript"), ("/js/models.js", "javascript"),
                           ("/mock/drains.json", "application/json"), ("/samples/blocked_drain.jpg", "image/jpeg"),
                           ("/css/styles.css", "text/css")):
            with self.subTest(path=path):
                r = httpx.get(f"{self.url}{path}")
                self.assertEqual(r.status_code, 200)
                self.assertIn(kind, r.headers["content-type"])

    def test_chunked_oversized_upload_is_cut_off_while_streaming(self):
        # No Content-Length: only the streaming byte counter can stop this request.
        boundary = "b0undary"
        sent = {"chunks": 0}

        def body():
            yield (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="big.png"\r\n'
                   "Content-Type: image/png\r\n\r\n").encode() + b"\x89PNG\r\n\x1a\n"
            for _ in range(64):  # 4 MiB in 64 KiB chunks
                sent["chunks"] += 1
                yield b"0" * 65536
            yield f"\r\n--{boundary}--\r\n".encode()

        calls = self.ollama.calls
        with patch.object(main, "MAX_IMAGE_BYTES", 100_000):
            r = httpx.post(f"{self.url}/analyze", content=body(), timeout=20,
                           headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        self.assertNotIn("content-length", {k.lower() for k in r.request.headers})
        self.assertEqual(r.status_code, 413)
        self.assertEqual(r.json()["error"]["code"], "IMAGE_TOO_LARGE")
        self.assertEqual(self.ollama.calls, calls)

    def test_upload_within_limit_still_streams_through(self):
        r = httpx.post(f"{self.url}/analyze", files={"image": ("d.png", base.PNG, "image/png")}, timeout=20)
        self.assertEqual(r.status_code, 200)

    def test_repo_internals_are_not_served(self):
        for path in ("/.git/config", "/backend/main.py", "/.venv/pyvenv.cfg", "/risk_engine/engine.py", "/js/../backend/main.py"):
            self.assertEqual(httpx.get(f"{self.url}{path}").status_code, 404, path)



class UploadLimitMechanism(unittest.TestCase):
    """Proves the cut-off happens while streaming (the endpoint's own size check cannot show that)."""

    def run_middleware(self, chunks, headers=()):
        import asyncio
        seen = {"bytes": 0, "disconnected": False}
        sent = []

        async def app(scope, receive, send):  # stands in for FastAPI: reads the whole body, then answers
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    seen["disconnected"] = True
                    break
                seen["bytes"] += len(message.get("body", b""))
                if not message.get("more_body"):
                    break
            await send({"type": "http.response.start", "status": 400, "headers": []})
            await send({"type": "http.response.body", "body": b"parser error"})

        queue = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]
        delivered = {"n": 0}

        async def receive():
            delivered["n"] += 1
            return queue.pop(0)

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "method": "POST", "path": "/analyze", "headers": list(headers)}
        with patch.object(main, "MAX_IMAGE_BYTES", 1000), patch.object(main, "UPLOAD_OVERHEAD_BYTES", 0):
            asyncio.run(main.UploadLimitMiddleware(app)(scope, receive, send))
        return seen, sent, delivered["n"]

    def test_stops_reading_once_the_limit_is_crossed(self):
        seen, sent, pulled = self.run_middleware([b"x" * 400] * 50)  # 20 000 bytes, no Content-Length
        self.assertTrue(seen["disconnected"])
        self.assertLessEqual(seen["bytes"], 1000)
        self.assertEqual(pulled, 3)  # 400 + 400 + 400 > 1000: nothing after the third chunk is read
        self.assertEqual(sent[0]["status"], 413)
        self.assertEqual(json.loads(sent[1]["body"])["error"]["code"], "IMAGE_TOO_LARGE")
        self.assertEqual(len(sent), 2)  # the app's own "parser error" response is suppressed

    def test_declared_length_is_refused_without_reading(self):
        seen, sent, pulled = self.run_middleware([b"x" * 10], headers=[(b"content-length", b"5000")])
        self.assertEqual((pulled, seen["bytes"]), (0, 0))
        self.assertEqual(sent[0]["status"], 413)

    def test_small_bodies_pass_through_untouched(self):
        seen, sent, _ = self.run_middleware([b"x" * 300, b"y" * 300])
        self.assertEqual(seen["bytes"], 600)
        self.assertEqual(sent[0]["status"], 400)  # whatever the app answered


if __name__ == "__main__":
    unittest.main()
