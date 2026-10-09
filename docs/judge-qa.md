# Judge Q&A (honest answers)

Every answer below matches the code in this repository. If a judge asks about something not listed, the safe
answer is "that is not implemented yet".

**What exactly does the model do?**
`vision/drain_analysis.py` sends the photo to `gemma3:12b`, a general vision-language model, running locally in
Ollama. A fixed prompt and a JSON schema ask whether the drain opening is visible, the image quality, whether material
obstructs the opening, a rough blockage percentage and warnings. The code validates every field and drops the
percentage if the model says it is uncertain or cannot see the opening. It is not a detector trained on drain images.

**Why is this better than manual inspection alone?**
It is not a replacement. It is triage: a photo from a field worker or citizen can be scored in seconds, the inspection
queue orders drains by risk, and each result explains its factors and assumptions. Unclear photos go to a
"needs manual inspection" group instead of being guessed. We have not measured time saved.

**What is the risk formula?**
Score = 100 × (0.45·blockage + 0.35·rainfall + 0.20·history) / (sum of weights used), where blockage is 0-1, rainfall
is a band value (NONE 0, LIGHT 0.2, MODERATE 0.5, HEAVY 0.8, VERY/EXTREMELY HEAVY 1.0 by mm/day) and history is
LOW 0.3 / MEDIUM 0.6 / HIGH 0.9. If history is unknown, its weight is dropped and the others renormalised.
Levels: ≤25 LOW, ≤50 MODERATE, ≤75 HIGH, else CRITICAL. Exact decimal arithmetic, rounded half up.

**Where do the weights come from?**
They are a design choice by the risk-engine author, giving blockage the largest share because it is the only input
observed from the image. They are not fitted to data and not calibrated against flood outcomes. Calibration needs
real flood and maintenance records.

**Why half-up rounding?**
The original float arithmetic rounded exact .5 scores inconsistently: 50.5 became 50 (MODERATE) while 25.5 and 75.5
rounded up. Half-up is deterministic and resolves every tie towards the higher category, which is the cautious
choice for triage. Tests check every input combination against an independent exact calculation.

**What is the safety override?**
A rule that blockage ≥70% with HEAVY or heavier rain is at least HIGH. With the current weights it never changes a
result, because the lowest such score is 66 (already HIGH). This is tested exhaustively. It stays as a guard in case
the weights change, and we do not claim it adds protection today.

**How reliable is the vision model?**
Unknown. We have two sample images and no labelled dataset. On those two, the blocked sample returned a positive
estimate (75% in our runs) and the clear sample returned "uncertain, opening not clearly visible". That is a
functional check, not accuracy. `docs/evaluation-plan.md` and `scripts/evaluate_vision.py` are ready for a labelled set.

**What happens when an image is unclear?**
The percentage is null, so the risk engine is not called. Score and level stay null, `blockage_detected` is null (never
"clear"), no alert fires, and the recommendation is manual inspection. The dashboard shows a neutral grey state and
puts the drain in the "Needs manual inspection" group.

**How is missing rainfall handled?**
There is no live rainfall feed. The operator can enter mm/day. If it is missing, the engine assumes MODERATE (a
cautious middle value) and labels it `ASSUMED_DEFAULT` in the API and "assumed rainfall" in the UI. An invalid value is
rejected with HTTP 400.

**What data is synthetic?**
The seven demo drains (locations, blockage, rainfall) and the historical vulnerability table
(`risk_engine/data/synthetic_history.csv`). Both are labelled in the API and UI. Demo drains never raise alerts. Uploaded
images and their vision results are real model outputs.

**How are false positives and false negatives addressed?**
False negatives (missed blockages) are the costly error, so uncertainty never becomes "clear" and unclear photos are
queued for inspection. False positives cost an unnecessary visit. The score shows its factors so an operator can judge
it. We have not measured either rate; the evaluation plan reports the false-clear rate first.

**Does it work without internet?**
Analysis does: vision (local Ollama), risk engine, API and the dashboard's styling are local. Only the map needs the
internet (Leaflet from a CDN and OpenStreetMap tiles); without it the map shows a notice and the KPIs, inspection queue
and analysis keep working. Mock mode (`/?mock=1`) needs no model.

**How would a municipality deploy this?**
Not done. Needed: real drain locations and IDs, a rainfall source, real maintenance and flood history to replace the
synthetic table, a labelled image set to validate the model, authentication, persistent storage, and a field-photo
workflow. Today it is a single-machine prototype with in-memory state.

**How could it scale?**
The API is stateless apart from in-memory caches. Production would move records and trend history to a database, run
inference on GPU workers behind a queue, and batch photos. None of this is built or load-tested.

**What evidence exists today?**
Automated tests for the API contract, validation, error handling, risk boundaries and the frontend data mapping (see
the README for commands). Real-model smoke tests on the two samples. Browser walkthroughs of the full upload flow. No
field trial, no accuracy study, no flood-outcome validation.

**What has not been validated?**
Vision accuracy, the weights and thresholds, whether scores correlate with real flooding, field usability, and
performance under load.
