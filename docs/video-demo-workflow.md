# Video demo workflow — 2 min 30 s screen recording

A production guide for recording a 150-second demonstration of the running dashboard with
synchronised narration. Every button label, expected result and technical statement below was
read directly from the code (`index.html`, `js/*`, `backend/*`, `vision/*`, `risk_engine/*`) or
produced by running the project. Nothing is invented.

**Ground rule for this recording:** the only genuinely real analysis is a local vision model
estimating visible blockage in an uploaded photo. Everything else on screen (drain records,
locations, rainfall, history) is synthetic or operator-supplied and is labelled as such in the
UI. The narration must keep that distinction visible at all times.

---

## 1. Architecture and user flow (concise)

**Stack.** A single FastAPI process (`backend/main.py`) serves both the dashboard (`GET /`) and
the JSON API. The frontend is dependency-free ES modules (`js/main.js`, `api.js`, `models.js`,
`ui.js`, `map.js`, `validate.js`, `config.js`) plus a Leaflet map loaded from a CDN. Scoring is
`risk_engine/`; image analysis is `vision/` calling a **local Ollama** multimodal model
(`gemma3:12b`, `vision/drain_analysis.py`).

**How one analysis is produced** (`POST /analyze` → `pipeline.process_vision_result`):

1. The request is validated (drain ID, lat/lon, rainfall) and the image is size-capped at
   10 MiB while it streams (`UploadLimitMiddleware`).
2. `vision.analyze_drain` runs in a worker thread and sends the image to the local Ollama
   model with a strict JSON schema and `temperature: 0`. It returns a **blockage percentage**
   or **`null`** when the opening is not clearly visible / the assessment is uncertain.
   `confidence` is **always `null`** — the model is told not to produce one.
3. **Completed** (numeric blockage): the risk engine computes
   `score = 100 × (0.45·blockage + 0.35·rainfall + 0.20·history) / (sum of weights used)`,
   exact decimal arithmetic, rounded half up (`risk_engine/engine.py`). Levels: **LOW ≤ 25,
   MODERATE ≤ 50, HIGH ≤ 75, CRITICAL above**. An alert fires for **HIGH and CRITICAL only**
   (`pipeline.ALERT_LEVELS`).
4. **Inconclusive** (`null` blockage): the risk engine is **not called**; score and level stay
   `null`, `blockage_detected` is forced to `null` (never "clear"), no alert, manual inspection
   recommended.
5. **Error** (Ollama unreachable/unusable): HTTP 502 `VISION_SERVICE_ERROR` — the drain is never
   reported as clear.

Every outcome returns the **same envelope** (`processing_status`, `vision`, `risk`, `rainfall`,
`alert`, `drain`, `error`) — see `docs/api-contract.md`.

**Real user journey (what you will record):** open `/` → header shows *Backend connected* and
the KPI strip / map / inspection queue load from `GET /drains` → in *Analyse a drain image*
pick a photo (button, drag-and-drop, or *Try a sample*) → optionally set a Drain ID, click the
map for coordinates, enter rainfall → *Run analysis* → *Analysis details* shows a spinner
("Analysing image with the local vision model…") → the result renders (score, level, factors,
recommendation, alert banner) → the record joins the queue and map → the what-if simulator,
queue and map are explored → inconclusive / error states handled honestly.

---

## 2. What is real vs synthetic vs assumed (say this out loud)

| On screen | Provenance | Where it comes from |
|---|---|---|
| Blockage % + warnings for **your uploaded image** | **Real** (local model) | `vision.analyze_drain` via Ollama `gemma3:12b` |
| Score, level, factors, recommendation for **that image** | **Real engine, real inputs** | `risk_engine` (weights are design choices, not calibrated) |
| The **7 starting drains** (D-001…D-017), their scores, levels, locations | **Synthetic demo data** | `backend/demo_drains.py` — invented coords/blockage/rainfall, scored by the real engine |
| Map coordinates of the demo drains | **Synthetic** (dashed ring) | same |
| Historical vulnerability (`synthetic_history.csv`) | **Synthetic** | `risk_engine/data/synthetic_history.csv`, 12 invented rows |
| Rainfall you type in | **Operator-supplied** (no live feed) | form field |
| Rainfall left blank | **Assumed** MODERATE, labelled "Assumed default" | `config.DEFAULT_RAIN_IF_MISSING` |
| Everything under `/?mock=1` | **Mock fixtures** (badge + `[MOCK]`) | `mock/*.json` |

**Verified initial state** (computed with the project's own engine — these are the numbers you
will actually see at the start of the recording):

- KPIs: **Drains 7 · Critical 2 · High 2 · Moderate 0 · Low 2 · Needs inspection 1**, and the
  note "7 of 7 records are synthetic demo data…".
- Queue, highest score first: **Act first** → D-001 (91, CRITICAL), D-017 (83, CRITICAL),
  D-006 (62, HIGH), D-003 (60, HIGH). **Needs manual inspection** → D-005 (inconclusive).
  **Schedule** → empty. **Routine** → D-010 (22), D-002 (18).
- Map: **6 markers plotted** (D-010 has no coordinates and is queue-only); all carry the
  synthetic dashed ring; D-005 is the grey **"?"** marker.

---

## 3. Prerequisites and pre-recording setup (all verified on this machine)

1. **Ollama present with the model.** `ollama list` shows `gemma3:12b` (8.2 GB) installed, and
   the Ollama server is reachable at `http://127.0.0.1:11434`. If not: `ollama serve` (or the
   Ollama desktop app).
2. **Backend + dashboard** from the repository root:
   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```
   Open <http://127.0.0.1:8000/>. The header must read **Backend connected** (green dot).
3. **Internet for the map only.** Leaflet loads from unpkg and tiles from OpenStreetMap. Without
   it the map shows a notice but KPIs/queue/analysis still work.
4. **Clean state.** Uploaded drains and trend history are **in memory**; restart the server right
   before recording so the queue is exactly the 7 demo drains and the first real reading trends
   as `NEW`.
5. **Warm the model before you hit record.** Run the blocked-drain analysis once and discard it.
   The first Ollama call loads the 8 GB model and is the slowest; a warm call is faster.
6. **Measure real warm-inference time on the recording laptop** during that warm-up. This tells
   you how much of the "waiting" segment the editor must compress (see §7). The code comments
   record CPU-only inference of this model reaching **~355 s** and "up to ~6 minutes" on a 16 GB
   laptop (`backend/main.py`, `vision/drain_analysis.py`).
7. **Screen width ≥ 1280 px** so the three-column layout (analysis · map · queue) is fully
   visible.

---

## 4. Exact UI controls and expected visible results

### Header
- Title **AI Urban Flood Sentinel**; subtitle "…experimental, not a flood forecast".
- Health chip: **"Checking backend…" → "Backend connected"** (polled every 15 s). "Backend
  unreachable" if the API stops; "Mock mode · no backend" only under `?mock=1`.
- **"Mock data"** badge is hidden unless `?mock=1`.

### KPI strip
Six tiles — **Drains, Critical, High, Moderate, Low, Needs inspection** — recomputed from
`/drains`. Critical/High/Needs inspection are tinted when non-zero.

### "Analyse a drain image" (left panel)
- **Dropzone** "Choose a drain photo / or drop it here / JPEG, PNG, WebP, GIF or BMP · up to
  10 MB". Clicking opens the file picker; after selection it shows the **image preview** and
  file meta ("name · NNN KB · click to change").
- **"Try a sample:"** → buttons **"Blocked drain"** and **"Clear drain"** (loads
  `samples/blocked_drain.jpg` / `samples/clear_drain.jpg` from the repo's `data/` folder).
- **Drain ID** field, placeholder "e.g. DEMO-1", label "Drain ID (optional; needed to list and
  map the result)". *Always give an ID in the demo, otherwise the result is shown but not added
  to the queue or map.*
- **"Location and rainfall (optional)"** expandable: **Latitude**, **Longitude** ("Click the map
  to fill these in. Left blank, no location is invented."), and **Rainfall (mm/day)** ("There is
  no live rainfall feed…").
- **"Run analysis"** button — disabled until an image is chosen; while running it becomes a
  spinner + **"Analysing…"** and cannot be clicked twice. Hint text: "Choose an image to enable
  analysis." / while busy "The local model usually takes 5–20 seconds." (see the caution in §8).
- Client-side validation messages appear in the red line above the button, e.g. "Enter both
  latitude and longitude, or neither.", "Rainfall must be a number of 0 or more (mm/day)."

### "Analysis details" (result panel)
- Waiting: "Select a drain on the map or in the queue, or analyse an image."
- Loading: spinner + **"Analysing image with the local vision model…"**.
- **Completed:** drain ID, coloured level badge (LOW/MODERATE/HIGH/CRITICAL), provenance chips
  (e.g. **"Real image analysis (local model)"**), the **score bar** "NN / 100 flood-risk score"
  with the caption "Experimental composite of blockage, rainfall and history. Not a probability
  of flooding.", a **Recommended action** callout, and a fact list: Blockage ("rough visual
  estimate, not a measurement"), Blockage detected, Rainfall, History, Trend (first reading =
  "● New"), Alert, **Model confidence: "Not provided"** ("the model gives no calibrated
  confidence"), Location, plus **Contributing factors** and a **Warnings and limitations**
  disclosure.
- **Inconclusive:** "Inconclusive: manual inspection required" + "The image could not be
  assessed reliably. This is not evidence that the drain is clear, and no flood-risk score was
  calculated." The Warnings block auto-opens; the simulator is hidden.
- **Error:** "Processing error" with the `error.code`, message and a **"Retry"** button.

### What-if simulator (appears only for a scored result with a blockage figure)
- Header "What-if simulator" + violet **"HYPOTHETICAL"** tag; intro "…Not a forecast; never
  raises an alert; the real result is not changed."
- **Blockage** slider (0–100 %) and **Rainfall** slider (0–250 mm/day).
- **"Run scenario"** and **"Reset to baseline"** buttons. Output shows Baseline vs Hypothetical
  scores/levels, the score delta, any category change and the changed inputs. Instant — it only
  runs the risk engine, no model call.

### Map (centre)
Risk-coloured markers (backend level), grey **"?"** for needs-inspection, dashed ring for
synthetic demo locations, bottom-left legend ("Risk level (from the backend)… Markers are point
estimates for a drain, not a flood extent."). **Clicking the map fills Latitude/Longitude** in
the form (6 decimals) and opens the Location panel. Marker click selects the drain.

### Inspection queue (right)
Groups **Act first / Needs manual inspection / Schedule / Routine**, each row showing the score
badge (or "?"/INSPECT), drain ID, the engine's recommendation, and flags: **"analysed image"**,
**"synthetic demo record"**, **"synthetic history"**, **"assumed rainfall"**, **"no
coordinates"**. Row click selects the drain and loads its detail.

### Footer
"Scores are experimental composite estimates, not flood probabilities. Sample images: sources
and licences."

---

## 5. Recommended sample selection

- **Centre-piece real analysis:** **"Blocked drain"** sample, **Drain ID `DEMO-1`**, **rainfall
  `90`**, location by **clicking the map**. `DEMO-1` is not in the synthetic-history table, so
  the result honestly shows *History unavailable* and the flag **"analysed image"** (not
  "synthetic history"). With a high blockage and HEAVY rain the score lands in HIGH/CRITICAL, so
  an **alert banner** appears — but narrate the mechanism, not a fixed number, because the model
  returns a different percentage each run.
- **Inconclusive path:** **"Clear drain"** sample (the model frequently reports the opening is
  not clearly visible → inconclusive). Because the model's answer varies, present the *rule* ("no
  usable estimate ⇒ no score, no alert"), not a guaranteed outcome. If a second real run does
  not fit the runtime budget, point to the **synthetic** demo drain **D-005** and label it as a
  synthetic record.
- **Instant, dependable segments** (no model, always available): the KPI strip, the map, the
  inspection queue, and the **what-if simulator** on the scored DEMO-1 result. Lean on these to
  fill time safely.

---

## 6. Ordered screen-recording checklist

Follow in order; each step lists the control and the result you should see.

1. **Launch & landing.** Backend running; open `/`. Confirm **"Backend connected"**, KPIs
   7/2/2/0/2/1, six map markers, four-group queue. *(Narrate overview + that the 7 records are
   synthetic.)*
2. **Tour the queue and map.** Hover/click one **Act first** row (e.g. D-001) to show the detail
   panel for a synthetic record ("Drain · synthetic record", "Synthetic demo record" chip). Point
   at the grey **"?"** D-005 marker and the **no-coordinates** D-010 row.
3. **Start a real analysis.** Click **"Blocked drain"**. Preview + file meta appear; **"Run
   analysis"** becomes enabled.
4. **Add context.** Type Drain ID **`DEMO-1`**. Expand **"Location and rainfall (optional)"**.
   **Click the map** to fill Latitude/Longitude. Enter Rainfall **`90`**.
5. **Run.** Click **"Run analysis"**. The button turns into a spinner **"Analysing…"** and the
   detail panel shows **"Analysing image with the local vision model…"**. *(This is the slow
   step — see §7.)*
6. **Result.** When it returns: level badge, **score bar** "NN / 100", **"Real image analysis
   (local model)"** chip, blockage labelled "rough visual estimate, not a measurement", **Model
   confidence: Not provided**, contributing factors, recommendation callout, and — if HIGH/
   CRITICAL — the **alert banner** at the top. Scroll to the **Warnings and limitations** block.
7. **It joined the fleet.** Show the queue now contains **DEMO-1** with the **"analysed image"**
   flag, the new selected marker on the map, and updated KPI counts.
8. **What-if simulator.** With DEMO-1 selected, drag **Blockage** and **Rainfall**, click **"Run
   scenario"**, and show Baseline vs Hypothetical + score delta. Emphasise: hypothetical, no
   alert, real result unchanged.
9. **Inconclusive / error honesty.** Either run the **"Clear drain"** sample as `DEMO-2` and
   narrate whatever the model returns (inconclusive → grey badge, no score, warnings open), or
   show the synthetic **D-005** and/or describe the error panel ("Processing error", code,
   **Retry**) — e.g. `VISION_SERVICE_ERROR` if Ollama is stopped, `INVALID_INPUT` for a
   non-image, `IMAGE_TOO_LARGE` over 10 MiB.
10. **Close on limitations.** Point at the footer and the "not a probability of flooding"
    caption: experimental, synthetic history/demo data, no live rainfall, in-memory prototype.

---

## 7. Timing plan for a 150-second cut

The only step with variable, potentially minutes-long duration is step 5 (real inference). Every
other interaction is sub-second. Budget:

| Segment | Clock | ~Time | Notes |
|---|---|---|---|
| 1. Landing, KPIs, synthetic-data caveat | 0:00–0:15 | 15 s | Instant |
| 2. Queue + map tour | 0:15–0:35 | 20 s | Instant |
| 3–4. Real upload: sample → DEMO-1 → map click → rainfall 90 | 0:35–0:55 | 20 s | Instant |
| 5. "Run analysis" wait | 0:55–1:25 | 30 s | **Compress the real wait in editing** |
| 6. Result walkthrough + alert | 1:25–1:50 | 25 s | Instant once returned |
| 7. Queue/map update with DEMO-1 | 1:50–2:00 | 10 s | Instant |
| 8. What-if simulator | 2:00–2:15 | 15 s | Instant |
| 9. Inconclusive / error honesty | 2:15–2:25 | 10 s | Synthetic D-005 or a pre-captured real inconclusive |
| 10. Limitations + close | 2:25–2:30 | 5 s | Instant |

**Handling the slow inference honestly (step 5):**
- Record the button click and the spinner, then **in editing compress the dead wait** (speed-up
  or a cut) **while narration explains the truth**: "the blockage estimate comes from a local
  8-billion-parameter vision model running on this laptop's CPU; on this hardware a single image
  takes on the order of a minute or two." Do **not** speed it up so far that it reads as
  "instant", and do **not** paste in a pre-baked result as if it were live.
- If the measured warm inference is short enough to keep live, keep it live — it is the most
  credible shot. If it runs long, the honest compress-plus-narration is the correct treatment.
- The in-app hint "The local model usually takes 5–20 seconds" is **optimistic** relative to the
  measured CPU figures in the code comments; do not repeat "5–20 seconds" as a claim in the
  narration.

---

## 8. Screen transitions and UI details worth capturing

- The **health chip** flipping "Checking backend…" → "Backend connected" on load.
- The **dropzone preview** appearing with file meta after "Blocked drain".
- The **map click auto-filling** Latitude/Longitude and expanding the Location panel.
- The **"Run analysis" → spinner "Analysing…"** button state and the panel's "Analysing image
  with the local vision model…" message (this is your visual anchor during the wait).
- The **auto-scroll** to the Analysis details panel when the result lands (`revealDetails`).
- The **alert banner** sliding in at the very top (only for HIGH/CRITICAL).
- The **provenance chips** ("Real image analysis (local model)" vs "Synthetic demo record").
- The **queue row** for DEMO-1 appearing with the **"analysed image"** flag, and its map marker
  getting the selected ring.
- The **KPI numbers changing** after the real record is added.
- The **what-if panel** with its violet **HYPOTHETICAL** tag and the two-column Baseline →
  Hypothetical comparison.
- The **Warnings and limitations** disclosure auto-opening on an inconclusive result.

---

## 9. Handling inconclusive images, timeouts and errors (be honest)

- **Inconclusive** (`processing_status: inconclusive`): no score, no level, grey "INCONCLUSIVE"
  badge, `blockage_detected` shown as "Unknown", manual-inspection recommendation, warnings open.
  The vision model returns a `null` percentage for **both** "uncertain" and "no blockage seen",
  so a clear drain also reads as inconclusive — the system **cannot** currently express
  "confirmed clear". Say exactly that.
- **Timeout:** the browser aborts at **620 s** (`ANALYZE_TIMEOUT_MS`), just above the backend's
  **600 s** vision timeout; the panel shows a `TIMEOUT` error "The request timed out." and the
  Retry button. On a slow laptop a genuine timeout is possible if the model is cold — keep the
  Retry path in your back pocket.
- **Ollama down / unusable:** HTTP **502 `VISION_SERVICE_ERROR`** — "The vision service is
  unavailable or returned an unusable response. The drain was not assessed; this is not a
  clear-drain result." Restart Ollama and press **Retry**. Never let a service failure look like
  a clear drain.
- **Bad input:** HTTP **400 `INVALID_INPUT`** (non-image file, negative rainfall, mismatched
  lat/lon), **413 `IMAGE_TOO_LARGE`** over 10 MiB, **422 `INVALID_REQUEST`** if `image` is
  missing.
- **Backend restart mid-recording:** the page detects it within ~15 s, reconnects and reloads
  the queue; earlier uploads are gone (in-memory). Restart deliberately before recording, not
  during.

---

## 10. Claims you CAN make vs MUST NOT make

**Supported by the implementation (safe):**
- "A local vision model estimates visible blockage from a drain photo." (`vision/drain_analysis.py`)
- "The score is an explained weighted composite of blockage (45 %), rainfall (35 %) and history
  (20 %), shown with its contributing factors." (`risk_engine/engine.py`, `config.py`)
- "Levels are LOW/MODERATE/HIGH/CRITICAL by score thresholds; alerts fire only for HIGH and
  CRITICAL." (`config.py`, `pipeline.ALERT_LEVELS`)
- "Unclear images are refused a score and referred to manual inspection, rather than guessed."
  (`pipeline.process_vision_result`)
- "Assumptions are labelled: operator rainfall vs assumed default, synthetic history, synthetic
  demo records." (`models.js`, `pipeline`, `demo_drains.py`)
- "The what-if simulator reuses the same engine, is hypothetical, and never raises an alert or
  changes the real result." (`risk_engine/what_if.py`)
- "The model gives no calibrated confidence — confidence is always 'Not provided'."
  (`vision/drain_analysis.py`, UI fact "Model confidence")
- "The dashboard, risk engine, API and mock mode run offline once installed; only the map needs
  the internet." (README)

**Must NOT be made (not supported):**
- No "predicts floods", no flood **probability**, no timing/extent of flooding. Scores rank
  drainage condition only. (Footer + METHODOLOGY.md)
- No accuracy, precision, recall or F1 numbers — **no labelled evaluation set exists**; vision
  accuracy is unmeasured. (`docs/evaluation-plan.md`)
- No "live rainfall" — the operator types mm/day; there is **no live feed**.
- No "real city data" — the 7 demo drains, their locations and `synthetic_history.csv` are
  invented.
- No "instant" or "real-time" analysis; CPU inference is minutes on this-class hardware.
- No deployment, partners, customers or field trials.
- Do not present the **7 demo drains** or any **`?mock=1`** screen as a real analysis.
- Do not call the two sample images an evaluation set — they are example inputs.

---

## 11. Narration outline (grounded — fill wording, not facts)

1. **Problem (15 s):** crews can't inspect every drain before heavy rain; the question is *which
   drain first, and why*. This tool turns one drain photo into an explained inspection priority.
2. **Overview (20 s):** KPI strip, map, inspection queue — and say plainly that the **7 starting
   records are synthetic demo data** used to show the triage layout.
3. **Real analysis setup (20 s):** "Blocked drain" sample, Drain ID DEMO-1, click the map for a
   location, rainfall 90 — "rainfall is entered by an operator; there is no live feed."
4. **The wait (30 s, honest):** "Run analysis" → "the local vision model is estimating visible
   blockage; on this laptop's CPU that's on the order of a minute or two" *(match the real
   measured time; do not say 'instant' or '5–20 seconds')*.
5. **Result (25 s):** the estimate is "a rough visual **estimate, not a measurement**"; model
   confidence is "not provided"; the engine combines it with rainfall and (synthetic) history
   into an explained score — "not a probability of flooding" — with a recommended action and an
   alert only because the backend triggered it for HIGH/CRITICAL.
6. **It joins the fleet (10 s):** DEMO-1 now appears in the queue flagged "analysed image" and
   on the map, alongside the clearly-labelled synthetic records.
7. **What-if (15 s):** same engine, hypothetical only, no alert, real result untouched.
8. **Honesty beat (10 s):** an unclear image gets **no score** and goes to manual inspection —
   that's a feature, not a failure; and errors (model down, bad file) surface explicitly with a
   Retry, never as a "clear" drain.
9. **Close (5 s):** experimental prototype — synthetic history/demo data, no live rainfall,
   unmeasured accuracy, in-memory — built to make triage **explainable**, not to predict floods.

---

## 12. Issues that could disrupt the recording

- **Slow / variable inference.** The dominant risk. Cold model can take minutes; even warm runs
  vary and the model returns a **different blockage % each run**, so the final score/level is not
  fixed. Plan the edit around a compressed wait; never promise a specific score.
- **Optimistic in-app hint** ("usually takes 5–20 seconds") contradicts the measured CPU figures
  — don't repeat it as a claim.
- **Internet dependency for the map.** Leaflet (unpkg) and OSM tiles need connectivity; without
  them the map shows a notice (queue/KPIs still fine). Test before recording.
- **15 s health polling** and the reconnect logic can briefly flip the header; harmless but
  capture a clean "connected" state.
- **In-memory state.** A restart wipes uploaded drains and trend; trend shows "New" on the first
  reading of a given ID and changes on re-runs — re-running DEMO-1 mid-take alters the trend
  shown.
- **Result without a Drain ID** is shown but **not** added to the queue or map — always type
  `DEMO-1`.
- **Auto-scroll** on result/error can move the view; frame the Analysis details panel generously.
- **Mock mode** must not be used for any "real" claim; it is for rehearsal only (badge + `[MOCK]`).

---

## 13. Verification status (what was actually run for this guide)

- **Python test suite:** `python -m unittest discover -t . -s .` → **Ran 121 tests … OK**
  (exit code 0). The model is stubbed by the tests, so Ollama is not required for them.
- **Node frontend tests:** `node --test "tests/js/*.test.mjs"` → **30 pass, 0 fail** (Node
  v24.12.0).
- **Environment:** `.venv` present; `ollama list` shows `gemma3:12b` (8.2 GB) installed and the
  Ollama server reachable at `http://127.0.0.1:11434`.
- **Live demo-drain scores** computed with the project's own engine match `mock/drains.json`
  exactly (D-001 91 CRITICAL, D-002 18 LOW, D-003 60 HIGH, D-005 inconclusive, D-006 62 HIGH,
  D-010 22 LOW, D-017 83 CRITICAL).
- **Not run / unverified for this guide:** a live end-to-end `POST /analyze` with real Ollama
  inference (the vision smoke test was not executed here), so the exact real-world inference
  time and the exact blockage % for the recording must be measured on the recording laptop
  during the warm-up in §3.
