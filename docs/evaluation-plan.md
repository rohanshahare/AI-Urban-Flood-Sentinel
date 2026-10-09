# Vision evaluation plan

**Status today:** no labelled dataset exists in this repository. The only images are the two samples in `data/`
(licences in `data/sources.md`), whose labels are provisional visual descriptions, not ground truth. **No accuracy,
precision or recall figures exist for this project, and none should be quoted.** This document says how to produce
them honestly.

## Smoke test vs. evaluation

`scripts/vision_smoke_test.py` runs the real model on the two sample images and checks that the **software** works:
the call succeeds and the output matches the contract. It does not measure accuracy, and passing it says nothing about
how often the model is right. Accuracy needs the labelled-set procedure below.

## What is being evaluated

`vision.analyze_drain` asks a general vision-language model (`gemma3:12b` via local Ollama) for a structured visual
assessment. Its output gives one of three outcomes, which `scripts/evaluate_vision.py` derives as:

| Outcome | How it is recognised in the output |
|---|---|
| `blocked` | `blockage_percentage` is a number |
| `inconclusive` | percentage is `null` and the module added its "do not interpret a negative result as proof…" warning |
| `not_blocked` | percentage is `null` without that warning (model saw the opening and no blockage) |
| `error` | `VisionInputError` / `VisionServiceError` |

Downstream, only `blocked` produces a risk score; `not_blocked` and `inconclusive` are both shown to users as
"inconclusive / manual inspection" (the API cannot yet say "confirmed clear").

## Dataset requirements

- Images the team has permission to use (own photos, municipal data shared with permission, or openly licensed).
- **At least 30 images per class** before reporting percentages; ideally 100+ and from several locations.
- Two labels: `blocked` (material visibly obstructs the opening) and `clear`. Optionally a human blockage estimate
  (0-100) for blocked images, ideally the average of two independent annotators.
- Variety that matches field use: day/night, wet/dry, different drain designs, angles, partial occlusion.
- Label **before** running the model, by someone who has not seen model output. Record annotator agreement.
- Keep a held-out set that is never used for prompt tuning.

## Procedure

1. Put images in a folder with `manifest.csv`: `image,label[,blockage_percentage]` (paths relative to the CSV).
2. Start Ollama with the model to be evaluated.
3. Run `python scripts/evaluate_vision.py path/to/manifest.csv --out eval_results.jsonl`
   (`--model` to compare another installed model). Raw outputs go to the JSONL file for audit (ignored by Git).
4. Record the model name, date, prompt version (Git commit) and hardware with the results.

## What to report

From the script's summary:

- **Counts table** (label × outcome, including inconclusive and error). Always report this.
- **Coverage**: share of images the model was willing to decide (not inconclusive / error).
- **Precision and recall for `blocked`** on decided images, each with its denominator.
- **False-clear rate**: blocked drains the model called `not_blocked`. This is the costly error for a maintenance
  tool, because an unflagged blocked drain is not inspected.
- **Percentage MAE** against human estimates, with its sample count.

Report counts and denominators, not just percentages. Below 30 images per class the script prints a caveat;
report counts only. Do not merge results from different model versions.

## Limitations to state with any result

- A general model, not one trained for drains; results may not transfer to other cities or drain designs.
- The blockage percentage is a visual estimate, not a measurement; `confidence` is never available.
- Results on a curated test set overstate field performance if field photos are worse.
- Vision accuracy says nothing about whether flooding occurs; the risk score is not validated against flood outcomes.
