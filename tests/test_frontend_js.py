"""Runs the Node frontend tests (tests/js) as part of the Python suite."""
import unittest


class FrontendTestsRun(unittest.TestCase):
    def test_node_suite(self):
        import shutil
        import subprocess
        from pathlib import Path
        node = shutil.which("node")
        if node is None:
            self.skipTest("node not installed; frontend tests not run")
        root = Path(__file__).resolve().parents[1]
        files = sorted(str(p) for p in (root / "tests" / "js").glob("*.test.mjs"))
        done = subprocess.run([node, "--test", *files], cwd=root, capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stdout[-3000:] + done.stderr[-1000:])


if __name__ == "__main__":
    unittest.main()
