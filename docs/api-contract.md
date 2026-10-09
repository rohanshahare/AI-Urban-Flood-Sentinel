# API Contract

Implemented in `backend/main.py` (routes) and `backend/pipeline.py` (response building).
Experimental prototype: scores are estimates, not validated flood predictions.

## Run and test

See the README for the full PowerShell walkthrough. Short form (repository root):

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m unittest discover -t . -s . -v    # Python tests + Node frontend tests (model stubbed)
node --test "tests/js/*.test.mjs"                               # frontend tests alone
.\.venv\Scripts\python.exe scriptsision_smoke_test.py        # real Ollama + gemma3:12b (not mocked)
```

Environment variables: `OLLAMA_URL` (default `http://127.0.0.1:11434`), `VISION_MODEL` (default `gemma3:12b`),
`VISION_TIMEOUT` seconds (default 180). Local prototype: no authentication; CORS admits only
`http://localhost[:port]` and `http://127.0.0.1[:port]` origins (the dashboard is served same-origin anyway).

## Endpoints

### `GET /health`
`200 {"status": "ok"}`

### `POST /analyze` (multipart/form-data)

| Field | Required | Meaning |
|---|---|---|
| `image` | yes | PNG, JPEG, WebP, GIF or BMP, max 10 MiB |
| `drain_id` | no | 1-64 chars of `A-Za-z0-9._-`. Enables synthetic history lookup and trend tracking |
| `lat`, `lon` | no | Both or neither. Validated (-90..90, -180..180). Never invented when absent |
| `rainfall_mm` | no | Rainfall in mm/day, >= 0. Operator-supplied: **the repository has no live rainfall feed** |

The vision call runs in a worker thread so it does not block the event loop.

Upload size (`UploadLimitMiddleware`, before multipart parsing): a declared `Content-Length` above 10 MiB + 64 KiB is
refused without reading the body; otherwise body bytes are counted as they stream in (chunked uploads included) and the
request is cut off with 413 as soon as the limit is crossed. The image is checked again after reading.

### `GET /drains`
JSON array of drain records (see below): 7 clearly labelled **SYNTHETIC** demo drains
(invented coordinates and measurements; risk values are computed by the real engine from them),
plus drains analysed through `/analyze` with a `drain_id` in this server session (`synthetic: false`, replacing a
demo drain with the same id; at most 100 are kept). One demo drain has `lat`/`lon` null and one is `inconclusive`.

### `GET /drains/{drain_id}`
The full unified envelope for one drain: the stored `/analyze` result, or for a synthetic demo drain a risk-only
breakdown (`vision.method` says "SYNTHETIC DEMO RECORD", `vision.blockage_detected` null, `rainfall.source`
`SYNTHETIC_DEMO`, `alert.triggered` always false: demo records never raise alerts). 404 error envelope if unknown.
The list and detail views of a drain always agree on status, level, score, blockage and coordinates.

### `POST /simulate` (application/json)
Hypothetical what-if comparison, computed by the existing risk engine (`risk_engine.what_if.simulate`, which calls
`assess_with_history` twice). It never raises an alert, is never stored and never writes trend history.

```json
{"drain_id": "D-017",
 "baseline": {"blockage_percentage": 82, "rainfall_mm": 90},
 "scenario": {"blockage_percentage": 40, "rainfall_mm": 30}}
```
`blockage_percentage` is required, a finite number 0-100; `rainfall_mm` is a finite number >= 0 or `null` (assumed
default, labelled). `drain_id` is optional and only selects the synthetic history record. Response:
`{"simulation": true, "label": "HYPOTHETICAL SIMULATION - ...", "drain_id", "baseline": <risk>, "scenario": <risk>,
"change": {"score_delta", "level_from", "level_to", "level_changed", "changed_inputs": [{"input","from","to"}]}}`
where `<risk>` has `flood_risk_score, risk_level, risk_factors, recommendation, warnings, inputs`. There is no
`processing_status` or `alert` field. Invalid input returns 400 with the standard error envelope.

## Unified response

Same top-level shape for every outcome:

```json
{
  "processing_status": "completed | inconclusive | error",
  "vision":   { "drain_id": null, "blockage_detected": null, "blockage_percentage": null, "confidence": null,
                "location": null, "timestamp": null, "method": null, "warnings": [] },
  "risk":     { "flood_risk_score": null, "risk_level": null, "risk_factors": [], "recommendation": null,
                "warnings": [], "trend": { "direction": "UNKNOWN", "change": null, "previous_score": null },
                "inputs": null },
  "rainfall": null,
  "alert":    { "triggered": false, "level": null, "title": null, "message": null, "recommendation": null },
  "drain":    { "drain_id": null, "lat": null, "lon": null, "processing_status": "...", "risk_level": null,
                "flood_risk_score": null, "blockage_percentage": null, "synthetic": false },
  "error":    null
}
```

Unavailable values are `null`, never zero or a default.

| Status | HTTP | Meaning |
|---|---|---|
| `completed` | 200 | Vision gave a numeric `blockage_percentage`; the risk engine scored it |
| `inconclusive` | 200 | `blockage_percentage` is null; **the risk engine is not called** |
| `error` | 4xx/5xx | Nothing was assessed; `error` is `{code, message}` |

### Completed
`vision` is passed through unchanged. `risk` holds the engine's score, level, factors, warnings and
recommendation. `risk.trend` is `NEW | RISING | FALLING | STABLE | UNKNOWN` (see Trend).
`alert.triggered` is true for `HIGH` and `CRITICAL`.
`rainfall` is `{mm_per_day, category, source}` where `source` is `REQUEST`, `ASSUMED_DEFAULT`
(mm_per_day null, category `MODERATE`) when none was supplied, or `SYNTHETIC_DEMO` (demo drains only). `risk.inputs` reports
`rainfall_source` (`PROVIDED | ASSUMED_MISSING | ASSUMED_INVALID`), `history_category` and `synthetic_data`.

### Inconclusive
`vision.blockage_detected` is **null** (not false), `vision.blockage_percentage` null, vision warnings
preserved, `risk.flood_risk_score` and `risk.risk_level` null, a manual-inspection recommendation,
`alert.triggered` false with `alert.level` null. `rainfall` echoes the request value (category null) or is null.
The vision component returns a null percentage both for uncertain images and for a "no blockage seen" result,
so a clear drain is also reported as inconclusive; the API cannot currently express "confirmed clear".

### Errors

| HTTP | `error.code` | Cause |
|---|---|---|
| 400 | `INVALID_INPUT` | Bad `drain_id`, `lat`/`lon`, `rainfall_mm`, or an empty/unrecognised image (`VisionInputError`) |
| 413 | `IMAGE_TOO_LARGE` | Image over 10 MiB |
| 422 | `INVALID_REQUEST` | Missing/invalid multipart field (e.g. no `image`) |
| 404 / 405 | `NOT_FOUND` / `METHOD_NOT_ALLOWED` | Unknown route or method |
| 502 | `VISION_SERVICE_ERROR` | Ollama unreachable or unusable model output (`VisionServiceError`). Never reported as a clear drain |
| 500 | `RISK_ENGINE_ERROR`, `INTERNAL_ERROR` | Server fault |

Messages are generic; details and tracebacks are logged server-side only. `/docs` serves the OpenAPI UI.

### Drain record (`/drains` item and `drain` field)
`drain_id, lat, lon, processing_status, risk_level, flood_risk_score, blockage_percentage, synthetic,
recommendation, rainfall_source, synthetic_history`. The last three say what a level rests on: the engine's
recommendation (or manual inspection), `rainfall_source` (`REQUEST`, `ASSUMED_DEFAULT`, `SYNTHETIC_DEMO` or null) and
`synthetic_history` (true/false, null when not scored). The dashboard's inspection queue uses them.

## Risk engine inputs and fallbacks

Inputs: blockage % (required, 0-100; else status `ERROR`), rainfall, historical vulnerability.
See `risk_engine/METHODOLOGY.md`.

- Rainfall missing -> assumed `MODERATE`, warning "not provided".
- Rainfall invalid (negative, NaN, inf, unknown text) -> assumed `MODERATE`, warning "invalid". At the API, an invalid `rainfall_mm` is rejected with 400 before reaching the engine.
- Scores use exact decimal arithmetic and round half up, so a score of exactly x.5 always rounds the same way.
- History unknown drain -> weights renormalised over blockage and rainfall, with a warning. Because blockage and rainfall then carry more weight, scores without history are not comparable to scores with it.

## Synthetic data and limitations

- `risk_engine/data/synthetic_history.csv` and the demo drains are synthetic. Nothing is calibrated on real flood outcomes. Warnings mark any result using them.
- Rainfall is supplied per request or assumed; there is no live feed.
- `blockage_percentage` is a rough visual estimate from a general vision-language model; `confidence` is always null.

## Trend

`risk.trend` = `{direction, change, previous_score}`, based on the previous valid score for the same `drain_id`:
first reading `NEW`; change >= +5 `RISING`; <= -5 `FALLING`; otherwise `STABLE`; `UNKNOWN` for no `drain_id`,
inconclusive or invalid readings (these are not logged). Trend never alters the score or level.
The log is **in memory, per process**: lost on restart, not shared between workers, capped at 20 readings per
drain and 500 drains. Each `/analyze` call with a `drain_id` adds a reading, including repeats of the same image.
