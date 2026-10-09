# AI Urban Flood Sentinel

AI-assisted drain inspection: a local vision model estimates visible blockage in a drain photo, a transparent risk
engine combines it with rainfall and (synthetic) history into an explained flood-risk score, and a dashboard turns the
results into an inspection queue, a map and a hypothetical what-if simulator, to help prioritise drain maintenance.

**Experimental.** Scores are composite heuristic estimates, not validated flood predictions or probabilities
(see [Known limitations](#known-limitations)).

## Components

| Path | Role | Owner |
|---|---|---|
| `vision/` | Drain image analysis with a local Ollama model (`gemma3:12b`) | Rohan |
| `risk_engine/` | Score, level, recommendation, synthetic history, trend, what-if simulation | Sanket |
| `backend/` | FastAPI app: API routes, validation, unified response, serves the dashboard | Risheeth |
| `index.html`, `css/`, `js/` | Dashboard: ES modules, local stylesheet, Leaflet map | Samrudh |
| `mock/` | Synthetic fixtures for explicit mock mode (made by `scripts/generate_mock_fixtures.py`) | |
| `data/` | Two sample drain images and their licences (`data/sources.md`) | |
| `tests/`, `risk_engine/tests/`, `tests/js/` | Python and Node tests | |
| `docs/` | API contract, architecture, demo guide, judge Q&A, pitch outline, evaluation plan, team handoff | |

## Run it (Windows PowerShell, from the repository root)

1. **Dependencies** (once). The project uses `.venv`; create it only if it is missing:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
   Python 3.10+. Node 22+ is needed only for the frontend tests.

2. **Ollama and the model** (default `gemma3:12b`):

   ```powershell
   ollama list
   ```
   `gemma3:12b` must be listed (otherwise `ollama pull gemma3:12b`, which needs internet once). Check the server:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:11434/api/tags
   ```
   If that cannot connect, run `ollama serve` (the Ollama desktop app also starts it).

3. **Start the backend** (it also serves the dashboard):

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```

4. **Open** <http://127.0.0.1:8000/>. Swagger UI: <http://127.0.0.1:8000/docs>. Health: <http://127.0.0.1:8000/health>.

Optional environment variables, set in the same window before step 3: `$env:OLLAMA_URL`, `$env:VISION_MODEL`,
`$env:VISION_TIMEOUT` (seconds, default 180).

**Mock mode** (rehearsal without the model or a real analysis): <http://127.0.0.1:8000/?mock=1>. It is never the
default, shows a "Mock data" badge, prefixes alerts with `[MOCK]`, labels every result "Mock fixture: not a real
analysis", and a failed real request never falls back to it. A panel lets you show the completed, inconclusive and
error fixtures.

**Internet:** only the browser needs it, for Leaflet (unpkg CDN) and OpenStreetMap tiles. Without tiles the map shows a
notice; without Leaflet the map area says so and the inspection queue still lists every drain. Styling is local.
Vision, risk engine, API, tests and mock mode run offline once installed.

## API routes

| Route | Purpose |
|---|---|
| `GET /` | Dashboard (`/css`, `/js`, `/mock`, `/samples` serve its static files) |
| `GET /health` | `{"status": "ok"}` |
| `GET /drains` | Drain records: 7 synthetic demo drains plus drains analysed with a drain ID this session |
| `GET /drains/{id}` | Full result envelope for one drain (404 envelope if unknown) |
| `POST /analyze` | Multipart: `image` (required), `drain_id`, `lat` + `lon`, `rainfall_mm` |
| `POST /simulate` | JSON what-if: baseline vs scenario, same risk engine, never an alert |
| `GET /docs`, `/openapi.json` | Swagger UI and schema |

Every analysis response has the same envelope: `processing_status` (`completed` / `inconclusive` / `error`),
`vision`, `risk`, `rainfall`, `alert`, `drain`, `error`. Full contract: [docs/api-contract.md](docs/api-contract.md).

## Test it

```powershell
.\.venv\Scripts\python.exe -m unittest discover -t . -s . -v
```
All Python tests, plus the Node frontend suite through a wrapper test. The model is stubbed (a fake Ollama HTTP server
and patched calls), so Ollama is not needed. The tests are read-only: they do not modify `mock/` or other project files.

```powershell
node --test "tests/js/*.test.mjs"
```
Frontend data mapping, API client, validation (Node 22+).

```powershell
.\.venv\Scripts\python.exe scripts\vision_smoke_test.py
```
**Real** Ollama inference on the two sample images. This checks that the software works with the model; it is not an
accuracy measurement.

Other scripts: `scripts\generate_mock_fixtures.py` (rewrite `mock/*.json` after a deliberate scoring change) and
`scripts\evaluate_vision.py manifest.csv` (evaluate a **labelled** image set; none ships with the repository; see
[docs/evaluation-plan.md](docs/evaluation-plan.md)).

## Using the dashboard

- **Header:** product and backend status (connected / unreachable / mock).
- **KPI strip:** counts computed from `/drains`: total, Critical, High, Moderate, Low, Needs inspection. Inconclusive
  records are counted only under "Needs inspection". Critical, High and Needs inspection are tinted when non-zero.
- **Left column:** analyse a photo (choose, drop, or use a sample), optional drain ID, location (click the map) and
  rainfall; then the result details and, for scored results, the what-if simulator.
- **Map:** markers use the backend risk level; grey "?" = needs inspection; a dashed ring = synthetic demo location.
  Drains without coordinates are never plotted, but they are listed in the queue.
- **Inspection queue (right):** every drain grouped as **Act first** (CRITICAL, HIGH), **Needs manual inspection**
  (inconclusive: unknown risk is not buried below known lower risk), **Schedule** (MODERATE), **Routine** (LOW), highest
  score first, with the engine's recommendation and flags such as "analysed image", "synthetic demo record",
  "synthetic history", "assumed rainfall", "no coordinates". It orders work and never changes a score.
- Colours mean the same everywhere: green LOW only, amber MODERATE, orange HIGH, red CRITICAL, grey unknown. The
  simulator uses violet, a non-risk colour, for hypothetical values.

## What is real, synthetic, assumed

- **Real:** the vision result for an uploaded image (blockage estimate, warnings) comes from the local model; the score,
  level, factors and recommendation come from the real risk engine for the inputs it was given.
- **Synthetic:** the 7 demo drains (locations, blockage, rainfall), `risk_engine/data/synthetic_history.csv`, and all mock
  fixtures. They are labelled in the API (`drain.synthetic`, `risk.inputs.synthetic_data`) and the UI; demo drains never
  raise alerts.
- **Rainfall:** **no live feed.** The operator enters mm/day. If it is missing, a cautious `MODERATE` is assumed and
  labelled "Assumed default"; an invalid value is rejected (HTTP 400).
- **History:** looked up by drain ID in the synthetic table. For an unknown drain, the history weight is dropped and the
  other weights renormalised, with a warning.

## How a result is produced

1. `POST /analyze` validates the image (format, size: 10 MiB, enforced while the upload streams) and the optional fields.
2. `vision.analyze_drain` runs in a worker thread and returns a blockage percentage, or `null` when the image cannot be
   assessed reliably.
3. **Completed:** score = 100 × (0.45·blockage + 0.35·rainfall + 0.20·history) / (sum of weights used), exact decimal
   arithmetic, rounded half up. Levels: LOW ≤25, MODERATE ≤50, HIGH ≤75, CRITICAL above. An alert fires for HIGH and
   CRITICAL only.
4. **Inconclusive:** the risk engine is **not** called; score and level stay `null`, `blockage_detected` is `null`
   (never "clear"), no alert, manual inspection recommended.
5. **Error:** `{code, message}` with HTTP 4xx/5xx; an unavailable model is never reported as a clear drain.

Method and rationale: [risk_engine/METHODOLOGY.md](risk_engine/METHODOLOGY.md).

## What-if simulator

For a scored result, sliders set a hypothetical blockage and rainfall. `POST /simulate` runs the same risk engine on the
baseline and the scenario and returns both, the score change, any category change and the changed inputs. It is
labelled hypothetical, never raises an alert, never changes the real result or trend history, and is not offered for
inconclusive results (there is no baseline score).

## Known limitations

- Not a flood forecast: scores rank drainage condition; they do not predict whether, when or where flooding happens.
- Vision accuracy is unmeasured (no labelled dataset); the blockage percentage is a rough visual estimate and
  `confidence` is always `null`. The vision output cannot distinguish "confirmed clear" from "uncertain", so both show
  as inconclusive.
- Weights and thresholds are design choices, not calibrated; levels are hard thresholds (a small input change near a
  boundary can change the level).
- No live rainfall; history and demo drains are synthetic.
- In-memory state: uploaded drains (max 100) and trend history (20 readings × 500 drains) reset on restart.
- Local prototype: no authentication; CORS admits only localhost origins. Map needs internet for Leaflet and tiles.
- A result without a drain ID is shown but not added to the queue or map.

## Documents

- [docs/demo-guide.md](docs/demo-guide.md): presenter sequence and fallbacks
- [docs/judge-qa.md](docs/judge-qa.md): honest answers to likely questions
- [docs/pitch-outline.md](docs/pitch-outline.md): presentation outline
- [docs/evaluation-plan.md](docs/evaluation-plan.md): how to measure vision accuracy (no results exist yet)
- [docs/team-handoff.md](docs/team-handoff.md): per-owner summary and review tasks
- [docs/api-contract.md](docs/api-contract.md), [docs/architecture.md](docs/architecture.md), [risk_engine/METHODOLOGY.md](risk_engine/METHODOLOGY.md)

## Team

- Rohan: Computer Vision
- Sanket: Flood Risk and Data Intelligence
- Risheeth: Backend and Integration
- Samrudh: Frontend, GIS, and Alerts
