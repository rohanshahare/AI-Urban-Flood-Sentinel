# AI Urban Flood Sentinel

A hackathon prototype for drain-blockage detection and early
urban flood-risk assessment.

## Components

- vision/: Drain image analysis and blockage detection
- backend/: API and application integration
- risk_engine/: Flood-risk assessment
- frontend/: Dashboard, GIS, and alert interface
- data/: Permitted sample and demonstration data
- tests/: Component and integration tests
- docs/: Architecture, API contracts, and test instructions

## Project status

Working vertical slice: image upload -> vision (Ollama) -> risk engine -> unified response -> dashboard.
Run and test commands, endpoints and the response contract are in `docs/api-contract.md`.
Historical vulnerability and the demo drains are synthetic; rainfall is supplied per request (no live feed).

## Team

- Rohan: Computer Vision
- Sanket: Flood Risk and Data Intelligence
- Risheeth: Backend and Integration
- Samrudh: Frontend, GIS, and Alerts
