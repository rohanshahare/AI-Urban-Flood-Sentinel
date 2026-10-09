# System Architecture

## Flow (implemented)

1. The user selects an image in the dashboard (`index.html`, `js/`), optionally with a drain ID, coordinates, rainfall.
2. `POST /analyze` (`backend/main.py`) validates the request and the image.
3. `vision.analyze_drain` runs in a worker thread against the local Ollama model.
4. `backend/pipeline.py` decides: a numeric blockage goes to the risk engine (`risk_engine`); `null` is
   *inconclusive* and bypasses scoring.
5. The backend returns one unified envelope (`processing_status`, `vision`, `risk`, `rainfall`, `alert`, `drain`, `error`).
6. `js/models.js` converts responses into display views with separate normalizers: `toAnalysisView` (analysis
   envelope), `toDrainDetailView` (`GET /drains/{id}`, must match the requested ID), `toDrainView` (`GET /drains` record),
   `toSimulationView` (`POST /simulate`) and `toMockFixtureView` (mock mode: always labelled synthetic). The map, KPIs,
   inspection queue, detail panel and alert banner all read these views, and colours come from one set of CSS risk
   classes, so they cannot disagree. Contract: `docs/api-contract.md`.

## Component ownership

- Vision: Rohan
- Risk engine: Sanket
- Backend integration: Risheeth
- Frontend and GIS: Samrudh

The implementation and component interfaces must be confirmed
with the relevant team members.
