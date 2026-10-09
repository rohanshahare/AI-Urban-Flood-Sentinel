"""Run real Ollama-backed smoke tests for the repository's sample drain images.

Run from the repository root:
    python scripts/vision_smoke_test.py

This validates the response contract; it intentionally does not assert that a
particular image must receive a particular classification.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vision import VisionInputError, VisionServiceError, analyze_drain  # noqa: E402
from vision.drain_analysis import DEFAULT_MODEL, DEFAULT_OLLAMA_URL  # noqa: E402

REQUIRED_FIELDS = {
    "drain_id",
    "blockage_detected",
    "blockage_percentage",
    "confidence",
    "location",
    "timestamp",
    "method",
    "warnings",
}


def validate_contract(result: Any) -> list[str]:
    """Return contract violations; an empty list means the shape is valid."""
    problems: list[str] = []
    if not isinstance(result, dict):
        return ["result is not a dictionary"]

    missing = REQUIRED_FIELDS - result.keys()
    if missing:
        problems.append(f"missing fields: {', '.join(sorted(missing))}")
        return problems

    if result["drain_id"] is not None and not isinstance(result["drain_id"], str):
        problems.append("drain_id must be str or None")
    if not isinstance(result["blockage_detected"], bool):
        problems.append("blockage_detected must be bool")

    percentage = result["blockage_percentage"]
    if percentage is not None:
        if isinstance(percentage, bool) or not isinstance(percentage, (int, float)):
            problems.append("blockage_percentage must be numeric or None")
        elif not math.isfinite(float(percentage)) or not 0 <= percentage <= 100:
            problems.append("blockage_percentage must be finite and between 0 and 100")

    # This implementation does not claim calibrated model confidence.
    if result["confidence"] is not None:
        problems.append("confidence should remain None until calibrated")

    location = result["location"]
    if location is not None:
        if not isinstance(location, dict) or set(location) != {"lat", "lon"}:
            problems.append('location must be None or a {"lat", "lon"} dictionary')
        else:
            for key, lower, upper in (("lat", -90, 90), ("lon", -180, 180)):
                value = location[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    problems.append(f"location.{key} must be numeric")
                elif not math.isfinite(float(value)) or not lower <= value <= upper:
                    problems.append(f"location.{key} is outside its valid range")

    if not isinstance(result["timestamp"], str) or not result["timestamp"]:
        problems.append("timestamp must be a non-empty string")
    if not isinstance(result["method"], str) or not result["method"]:
        problems.append("method must be a non-empty string")
    if not isinstance(result["warnings"], list) or not all(
        isinstance(item, str) for item in result["warnings"]
    ):
        problems.append("warnings must be a list of strings")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--images",
        nargs="+",
        type=Path,
        help="Image files to test (defaults to the two repository sample images).",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Installed Ollama model name.")
    parser.add_argument(
        "--ollama-url",
        default=DEFAULT_OLLAMA_URL,
        help="Ollama base URL (default: %(default)s).",
    )
    args = parser.parse_args()

    image_paths = args.images or [ROOT / "data" / "blocked_drain.jpg", ROOT / "data" / "clear_drain.jpg"]
    failures = 0

    print(f"Ollama URL: {args.ollama_url}")
    print(f"Model: {args.model}")
    print("Note: this checks inference and response shape, not detection accuracy.\n")

    for image_arg in image_paths:
        image_path = image_arg if image_arg.is_absolute() else (Path.cwd() / image_arg)
        image_path = image_path.resolve()
        print(f"=== {image_path} ===")
        if not image_path.is_file():
            print(json.dumps({"status": "FAIL", "error": "Image file not found."}, indent=2))
            failures += 1
            continue

        try:
            result = analyze_drain(
                image_path,
                drain_id=image_path.stem,
                model=args.model,
                ollama_url=args.ollama_url,
            )
            problems = validate_contract(result)
            print(json.dumps({"status": "PASS" if not problems else "FAIL", "result": result, "contract_issues": problems}, indent=2))
            if problems:
                failures += 1
        except (VisionInputError, VisionServiceError) as exc:
            print(json.dumps({"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)}, indent=2))
            failures += 1
        print()

    tested = len(image_paths)
    passed = tested - failures
    print(f"Smoke test summary: {passed}/{tested} passed; {failures} failed.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
