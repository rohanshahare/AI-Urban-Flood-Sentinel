"""mock/*.json must stay identical to what the real pipeline produces (see scripts/generate_mock_fixtures.py).

Read-only with respect to the repository: expected fixtures are built in memory and compared with the
checked-in files; the write path is exercised only inside a temporary directory.
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOCK = ROOT / "mock"
spec = importlib.util.spec_from_file_location("generate_mock_fixtures", ROOT / "scripts" / "generate_mock_fixtures.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def snapshot():
    return {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in MOCK.glob("*.json")}


class MockFixtures(unittest.TestCase):
    def test_committed_fixtures_match_the_generator(self):
        expected = generator.build_fixtures()
        self.assertEqual({f"{name}.json" for name in expected}, {p.name for p in MOCK.glob("*.json")},
                         "mock/ and the generator disagree on which fixtures exist")
        for name, data in expected.items():
            committed = json.loads((MOCK / f"{name}.json").read_text(encoding="utf-8"))
            self.assertEqual(committed, json.loads(generator.serialize(data)),
                             f"mock/{name}.json is stale: run python scripts/generate_mock_fixtures.py")

    def test_checking_and_generating_never_touch_the_checked_in_fixtures(self):
        before = snapshot()
        generator.build_fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            generator.main(Path(tmp))  # the explicit write path, isolated
            written = sorted(p.name for p in Path(tmp).glob("*.json"))
        self.assertEqual(written, sorted(before))
        self.assertEqual(snapshot(), before)

    def test_fixtures_follow_the_contract_and_are_labelled_synthetic(self):
        top = {"processing_status", "vision", "risk", "rainfall", "alert", "drain", "error"}
        for name, status in (("completed-critical", "completed"), ("completed-low", "completed"),
                             ("inconclusive", "inconclusive"), ("error", "error")):
            data = json.loads((MOCK / f"{name}.json").read_text(encoding="utf-8"))
            self.assertEqual(set(data), top, name)
            self.assertEqual(data["processing_status"], status)
            self.assertTrue(data["drain"]["synthetic"] or status == "error", name)
        inconclusive = json.loads((MOCK / "inconclusive.json").read_text(encoding="utf-8"))
        self.assertIsNone(inconclusive["risk"]["flood_risk_score"])
        self.assertFalse(inconclusive["alert"]["triggered"])
        for record in json.loads((MOCK / "drains.json").read_text(encoding="utf-8")):
            self.assertTrue(record["synthetic"])


if __name__ == "__main__":
    unittest.main()
