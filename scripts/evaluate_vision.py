"""Evaluate the vision component against a labelled image set (see docs/evaluation-plan.md).

Run from the repository root, with Ollama running:
    python scripts/evaluate_vision.py path/to/manifest.csv --out eval_results.jsonl

manifest.csv columns: image,label[,blockage_percentage]
  image                 path relative to the manifest file
  label                 "blocked" or "clear" (human ground truth)
  blockage_percentage   optional human estimate, 0-100, for blocked images

Each image is analysed once with the real model; raw outputs are written to --out for audit.
The repository ships no labelled dataset, so no results exist until a team runs this on one.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The vision module appends this sentence whenever the model was uncertain or could not see the
# drain opening; it is the only way to tell "inconclusive" from "no blockage seen" in its output.
UNCERTAIN_MARKER = "do not interpret a negative result as proof"
MIN_MEANINGFUL_N = 30


def predicted_class(result: dict) -> str:
    """blocked | not_blocked | inconclusive, from one analyze_drain() result."""
    if result.get("blockage_percentage") is not None:
        return "blocked"
    if any(UNCERTAIN_MARKER in w for w in result.get("warnings", [])):
        return "inconclusive"
    return "not_blocked"


def summarize(rows: list[dict]) -> dict:
    """rows: {"label": "blocked"|"clear", "prediction": ..., "true_pct": float|None, "pred_pct": float|None}."""
    matrix = {label: {"blocked": 0, "not_blocked": 0, "inconclusive": 0, "error": 0} for label in ("blocked", "clear")}
    for r in rows:
        matrix[r["label"]][r["prediction"]] += 1
    tp, fn = matrix["blocked"]["blocked"], matrix["blocked"]["not_blocked"]
    fp, tn = matrix["clear"]["blocked"], matrix["clear"]["not_blocked"]
    decided = tp + fn + fp + tn
    errors = [abs(r["pred_pct"] - r["true_pct"]) for r in rows
              if r["prediction"] == "blocked" and r["true_pct"] is not None and r["pred_pct"] is not None]
    ratio = lambda a, b: round(a / b, 3) if b else None  # noqa: E731
    return {
        "n_images": len(rows),
        "confusion": matrix,
        "coverage": ratio(decided, len(rows)),  # share of images the model was willing to decide
        "precision_blocked": ratio(tp, tp + fp),
        "recall_blocked": ratio(tp, tp + fn),
        "false_clear_rate": ratio(fn, tp + fn),  # blocked drains called "not blocked": the costly error
        "percentage_mae": round(sum(errors) / len(errors), 1) if errors else None,
        "percentage_mae_n": len(errors),
        "caveat": None if len(rows) >= MIN_MEANINGFUL_N else
        f"Only {len(rows)} images: too few for reliable estimates; report counts, not percentages.",
    }


def read_manifest(path: Path) -> list[dict]:
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            label = (row.get("label") or "").strip().lower()
            if label not in ("blocked", "clear"):
                raise ValueError(f"{path}:{i}: label must be 'blocked' or 'clear'")
            pct = (row.get("blockage_percentage") or "").strip()
            rows.append({"image": path.parent / row["image"].strip(), "label": label,
                         "true_pct": float(pct) if pct else None})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path, default=Path("eval_results.jsonl"))
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    from vision import VisionInputError, VisionServiceError, analyze_drain
    kwargs = {"model": args.model} if args.model else {}
    rows = []
    with args.out.open("w", encoding="utf-8") as out:
        for item in read_manifest(args.manifest):
            try:
                result = analyze_drain(item["image"], **kwargs)
                prediction, pred_pct = predicted_class(result), result["blockage_percentage"]
            except (VisionInputError, VisionServiceError) as exc:
                result, prediction, pred_pct = {"error": str(exc)}, "error", None
            rows.append({"label": item["label"], "prediction": prediction, "true_pct": item["true_pct"], "pred_pct": pred_pct})
            out.write(json.dumps({"image": str(item["image"]), "label": item["label"], "prediction": prediction, "result": result}) + "\n")
            print(f"{item['image']}: label={item['label']} prediction={prediction}")
    print(json.dumps(summarize(rows), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
