# Flood Risk Assessment Engine

Estimates drainage-related flood risk for a drain from blockage severity, rainfall and
historical vulnerability. It is an experimental heuristic, **not** a calibrated or validated flood predictor.

## Method

1. Normalise inputs: blockage % to 0-1; rainfall (mm/day or category) to a band value; history category to a value.
2. Weighted score: blockage 45%, rainfall 35%, history 20% (`config.py`), scaled to 0-100. Computed with exact
   decimal arithmetic and rounded half up (float arithmetic used to round exact x.5 scores inconsistently, which
   could flip a score across a level boundary; `tests/test_engine.py` checks every input combination against an independent calculation).
3. Level from score: `<=25` LOW, `<=50` MODERATE, `<=75` HIGH, else CRITICAL. A score of 52 is HIGH.
4. Recommendation per level.
5. Warnings for assumed/invalid inputs, low confidence and synthetic data. `inputs` reports where rainfall and history came from.

| Rainfall (mm/day) | Category | Value |
|---|---|---|
| < 2.5 | NONE | 0.0 |
| < 15.6 | LIGHT | 0.2 |
| < 64.5 | MODERATE | 0.5 |
| < 115.6 | HEAVY | 0.8 |
| < 204.5 | VERY_HEAVY | 1.0 |
| above | EXTREMELY_HEAVY | 1.0 |

## Why half-up rounding

The old `int(round(float_score))` rounded exact .5 scores inconsistently because of float representation: exactly 50.5
(10% blockage, HEAVY rain, HIGH history) became 50 (MODERATE), while exactly 25.5 and 75.5 rounded up (26 MODERATE,
76 CRITICAL). Exact `Fraction` arithmetic with half-up is deterministic and resolves every tie toward the higher score,
the cautious direction for triage. Non-tie scores are unchanged. Levels are still hard thresholds, so a small input
change near a boundary can change the level (9.9% vs 10% blockage in the case above: 50 MODERATE vs 51 HIGH); the
dashboard always shows the score beside the level.

## Missing and invalid data

- Blockage missing/invalid/out of range: status `ERROR`, no score. Never defaulted.
- Rainfall missing: assumed MODERATE (cautious), `rainfall_source = ASSUMED_MISSING`.
- Rainfall invalid (negative, NaN, inf, bool, unknown text): assumed MODERATE, `ASSUMED_INVALID`, separate warning.
- History unavailable or invalid: the history term is dropped and the other weights are renormalised
  (0.45/0.80 and 0.35/0.80). This raises the influence of blockage and rainfall, so scores without history
  run higher than with a LOW history.

## Safety floor

If blockage >= 70% and rainfall >= HEAVY, the level is raised to at least HIGH. With the current weights and
thresholds the lowest such score is 66 (already HIGH), so this rule **never changes a result today**
(verified over all blockage 70-100 x rainfall x history combinations in `tests/test_engine.py`). It is kept as a
guard in case weights or thresholds are retuned, and is tested by retuning the weights.

## History (synthetic)

`data/synthetic_history.csv` holds invented per-drain records (previous floods, past blockages, low-lying).
Points: `min(floods, 2) + low_lying + (blockages >= 4)`; 3+ HIGH, 2 MEDIUM, else LOW. Every row is labelled
`SYNTHETIC`, and results using it carry a warning. No real flood records are included.

## What-if simulation

`what_if.simulate(baseline, scenario)` scores a drain as-is and with some inputs overridden, through the same
`assess_with_history` path, and returns both results plus the score delta, level change and changed inputs.
It never reads or writes the trend log. The API exposes it as `POST /simulate`; results are hypothetical
comparisons, not forecasts, and never raise alerts. (`what_if()` is the older fixed rainfall-scenario table.)

## Estimate versus prediction

A score ranks drainage-related risk from a visual blockage estimate, an assumed or supplied rainfall figure and
(synthetic) historical context. It is not calibrated against real flood outcomes and does not predict whether, when
or where flooding will happen, nor its extent.

## Trend

`trend.py` compares the new score with the previous valid score for the same drain: first `NEW`,
change >= +5 `RISING`, <= -5 `FALLING`, else `STABLE`; invalid assessments are `UNKNOWN` and not logged.
It runs after scoring and does not alter score or level. Storage is in-memory and per process
(lost on restart; capped at 20 readings per drain, 500 drains).

## Usage and tests

```powershell
python -m risk_engine.what_if                                  # rainfall scenarios for a sample drain
python -m unittest discover -t . -s risk_engine/tests -v       # from the repository root
```

```python
from risk_engine import assess_flood_risk, assess_with_history, assess_with_trend
```
