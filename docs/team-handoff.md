# Team handoff

All of this is uncommitted work on `hardening/final-demo` (base `bfe73d1`). Nobody has approved it yet: each owner
should review the items listed for them. Contract: `docs/api-contract.md`. Run/test commands: `README.md`.

## Rohan: vision (`vision/`)

- **Entry point:** `vision.analyze_drain(image, *, drain_id, location, model="gemma3:12b", ollama_url, timeout=180, max_image_bytes=10 MiB)`.
  Backend overrides via `OLLAMA_URL`, `VISION_MODEL`, `VISION_TIMEOUT`.
- **Output:** `drain_id, blockage_detected, blockage_percentage, confidence (always null), location, timestamp, method, warnings`.
- **Errors:** `VisionInputError` (bad image or metadata → HTTP 400), `VisionServiceError` (Ollama down, timeout or bad output → 502).
- **Uncertainty:** null percentage when the model is uncertain, cannot see the opening or image quality is poor, and
  also when it sees no blockage. The backend treats every null as inconclusive.
- **Changed, please review:** `drain_visible` is now type-checked like the other model fields. A string `"false"`
  was truthy and turned "drain not visible" into a scored positive. New test in `tests/test_drain_analysis.py`.
- **Evaluation:** `scripts/evaluate_vision.py` and `docs/evaluation-plan.md`. No labelled data exists, so there are no accuracy numbers.
- **Open question:** could the model output distinguish "confirmed clear" from "uncertain" (e.g. return
  `assessment_uncertain` in the result)? Today both are null, so the UI can never say "clear".

## Sanket: risk engine (`risk_engine/`)

- **Score:** `100 × Σ(value·weight) / Σweight` with weights blockage 0.45, rainfall 0.35, history 0.20. History is
  dropped and the rest renormalised when unknown. Levels ≤25 LOW, ≤50 MODERATE, ≤75 HIGH, >75 CRITICAL.
- **Rainfall bands (mm/day):** <2.5 NONE 0, <15.6 LIGHT 0.2, <64.5 MODERATE 0.5, <115.6 HEAVY 0.8, <204.5 VERY_HEAVY 1.0,
  else EXTREMELY_HEAVY 1.0. Missing → assumed MODERATE (`ASSUMED_MISSING`); invalid → assumed (`ASSUMED_INVALID`).
- **History:** synthetic CSV; points = min(floods, 2) + low_lying + (blockages ≥ 4) → ≥3 HIGH, 2 MEDIUM, else LOW.
- **Trend:** ±5 points; in memory, 20 readings × 500 drains; invalid/inconclusive readings are not logged.
- **What-if:** `what_if.simulate(baseline, scenario)` calls `assess_with_history` twice and never touches the trend log.
- **Changes needing your review:**
  1. **Rounding (`engine.py` step 4).** Was `int(round(float))`; now exact `Fraction` arithmetic with half-up.
     Evidence: the old code scored exact ties inconsistently. `10% / HEAVY / HIGH history` = exactly 50.5 → old 50
     (MODERATE), new 51 (HIGH); `30% / NONE / MEDIUM` = 25.5 → 26 both; `50% / VERY_HEAVY / HIGH` = 75.5 → 76 both.
     26 of the 129 exact ties in the integer grid differed from consistent rounding. Non-tie scores are unchanged.
     Tests: `FormulaTests` in `risk_engine/tests/test_engine.py` (full grid vs. an independent exact calculation, plus boundary ties).
  2. **Safety override.** Unchanged, documented as redundant under current weights (minimum score at
     blockage ≥70 + HEAVY is 66 = HIGH). Tested exhaustively and by retuning weights. Keep, remove or re-specify?
  3. **Rainfall provenance.** `inputs.rainfall_source` distinguishes PROVIDED / ASSUMED_MISSING / ASSUMED_INVALID.
  4. **`what_if.simulate`** is new; the old `what_if()` table is untouched.
  5. Your branch's `9417597` dual-mode imports are equivalent to the package-relative imports here.
- **Sensitivity to note in Q&A:** levels are hard thresholds; e.g. 9.9% vs 10% blockage (HEAVY rain, HIGH history)
  moves 50 → 51, MODERATE → HIGH (tested).

## Risheeth: backend (`backend/`)

- **Start:** `.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`.
- **Endpoints:** `GET /health`, `POST /analyze` (multipart), `GET /drains`, `GET /drains/{id}`,
  `POST /simulate` (JSON), `/docs`, `/` + `/css`, `/js`, `/mock`, `/samples` static files.
- **Flow:** `main.analyze` validates (`pipeline.parse_*`), runs vision in `asyncio.to_thread`, then
  `pipeline.process_vision_result` → `completed` (risk engine) or `inconclusive` (no scoring) → envelope.
- **Errors:** one envelope for every status, `error: {code, message}`. 400 INVALID_INPUT, 413 IMAGE_TOO_LARGE,
  422 INVALID_REQUEST, 404/405, 502 VISION_SERVICE_ERROR, 500 RISK_ENGINE_ERROR / INTERNAL_ERROR. No tracebacks or paths.
- **Changed, please review:**
  1. `UploadLimitMiddleware` (pure ASGI) replaces the Content-Length-only check. It counts body bytes while streaming
     and returns 413 once 10 MiB + 64 KiB is exceeded, including chunked uploads. Proven in `UploadLimitMechanism`
     tests and live with a 12 MiB chunked request.
  2. Drain records gained `recommendation`, `rainfall_source`, `synthetic_history` (additive).
  3. `/simulate` has an OpenAPI request-body schema (documentation only; validation unchanged).
- **Limits:** in memory: 100 uploaded drains, trend 20 × 500. No auth; CORS allows localhost origins only.
- **Tests:** `tests/test_api.py`, `test_hardening.py` (fake Ollama HTTP server, live uvicorn, streaming limit), `test_simulate.py`.

## Samrudh: frontend and GIS (`index.html`, `js/`, `css/`)

- **Entry:** `index.html` → `js/main.js` (ES modules) + `css/styles.css`. Your `24bfabc` structure is kept: header
  with health dot, KPI strip, analysis sidebar with detail states, Leaflet map and legend, mock dev-tools panel.
- **Modules:** `config.js` (real mode default, `?mock=1` opt-in), `api.js` (client, timeouts, no fallback),
  `models.js` (pure normalizers: analysis, drain detail, drain record, simulation, mock fixture; KPIs, inspection
  queue, provenance),
  `validate.js` (upload checks), `map.js`, `ui.js`.
- **KPIs and queue:** computed from `/drains` records via `riskKey()`, the same function that colours markers.
  The queue groups by backend level: Act first (CRITICAL/HIGH) → Needs manual inspection → Schedule → Routine.
- **Alerts:** banner only when the backend's `alert.triggered` is true for a completed result; cleared on new
  analysis, error or inconclusive; prefixed `[MOCK]` in mock mode.
- **Changed, please review:**
  1. Inspection queue replaces the flat drain list.
  2. Map tiles are greyscaled with CSS so OSM's red POI pins are not confused with risk markers.
  3. **Tailwind CDN removed**, replaced by a local design system in `css/styles.css` (tokens for every risk colour,
     shared by KPIs, badges, queue, markers and legend). Reasons: styling now works offline, no "not for production"
     console warning, and one colour definition instead of several shades per level (amber with white text failed
     contrast). Layout: three columns at ≥1280 px (analysis | map | queue), two at ≥768 px, one column on phones.
  4. The drain list reloads automatically when the backend comes back after a restart; a network error re-checks
     health immediately.
  5. `mock/*.json` are generated by `scripts/generate_mock_fixtures.py` in the real contract shape. They replace
     your original fixtures, which used a 0-1 score and a confidence value the pipeline never produces.
     `js/alerts.js` and `js/state.js` (empty stubs) were removed.
  6. Upload: drop zone with preview and file size, drag-and-drop, sample buttons; submit disabled until an image is
     chosen; accepted types limited to what the vision module supports (JPEG, PNG, WebP, GIF, BMP).
  7. Selection sync: the selected drain gets a ring on the map and a highlight in the queue; the details panel scrolls
     into view for a new result; a response for a drain clicked during an analysis can no longer overwrite the result.
  8. New normalizers `toDrainDetailView` (rejects a detail for a different drain) and `toMockFixtureView` (mock data is
     always labelled synthetic, including its rainfall).
  9. Accessibility: labelled simulator sliders, labelled map markers and queue rows, visible focus outlines,
     reduced-motion support.
- **Tests:** `tests/js/*.test.mjs` (`node --test`).
- **Known UX gaps:** Leaflet and tiles need internet; results without a drain ID are not added to the map or queue;
  in the 768-1279 px layout the analysis and queue share the left column (each scrolls).

## Everyone: test-suite fix

`tests/test_mock_fixtures.py` used to call the fixture generator, which ignored its output-directory argument and
**rewrote the checked-in `mock/*.json`** on every test run, then compared an empty temporary directory and so checked
nothing. The generator now has a pure `build_fixtures()`; the test compares in memory, exercises the write path only in a
temporary directory, and asserts that `mock/` is byte-for-byte and timestamp unchanged. A deliberately drifted fixture
now fails the test. Running the whole suite leaves `git status` and file contents unchanged.

## Integration notes for whoever merges

- `origin/main` (`24bfabc`) and this branch both changed `index.html`, `css/styles.css` and `js/*`; expect conflicts,
  and this branch's versions are the reconciled ones.
- `origin/sanket/flood-risk-engine` vs. this branch: same engine apart from the changes listed under Sanket.
