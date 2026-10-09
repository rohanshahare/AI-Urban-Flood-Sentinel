# Pitch outline

No official template or problem-statement text is in this repository; adapt this outline to the organisers' required
format and time limit. Every claim here is backed by the running prototype or stated as a limitation.

## 1. Title and value proposition
**AI Urban Flood Sentinel.** AI-assisted drain inspection combining image-based blockage assessment with explainable
flood-risk triage and hypothetical scenario analysis, to help prioritise drain maintenance.

## 2. Problem understanding
- Blocked storm drains make urban waterlogging during heavy rain worse.
- Maintenance teams cannot inspect every drain before every storm; they need to know **which drains to visit first**.
- Photos are easy to collect, but turning them into prioritised, explainable work is manual.
- (Add verified local context and sources from the official problem statement; do not quote figures without a source.)

## 3. Proposed solution
1. Upload a drain photo (optional ID, location and rainfall).
2. A local vision model gives a rough blockage estimate, or says it cannot tell.
3. A transparent risk engine combines blockage, rainfall and history into a 0-100 score, a level and a recommendation.
4. The dashboard shows a map, KPIs, an inspection queue ordered by risk, and an explained result.
5. A what-if simulator shows how risk would change with different rainfall or blockage.

## 4. Technical approach
FastAPI backend → `vision` (Ollama `gemma3:12b`, local) → `risk_engine` (weighted score 45/35/20, exact rounding,
trend, synthetic history) → one JSON envelope → dashboard (ES modules, Leaflet). Diagram: `docs/architecture.md`.

## 5. What is distinctive (our contribution, not the components)
- **Uncertainty is a first-class outcome:** unclear photos become "needs inspection", never "clear" or LOW.
- **Every score is explained and labelled by provenance:** real image, operator rainfall, assumed rainfall, synthetic history.
- **Prioritisation, not just detection:** the queue turns scores into an order of work.
- **Hypothetical vs. real are separated:** the simulator reuses the real engine but never raises alerts or changes records.
- **Runs locally:** no paid API or cloud service needed for analysis.

## 6. Working prototype evidence (live demo)
Follow `docs/demo-guide.md`: overview → real blocked-drain analysis → explanation and alert → inconclusive handling →
what-if → limits. Mention the automated tests and real-model smoke tests; show no accuracy figure (none exist).

## 7. Impact and feasibility
- Runs on one laptop with a local model; the data needed (photos, drain IDs, rainfall) is the kind a city already collects.
- Expected value: inspection effort directed at the riskiest drains first. **Not yet measured.**

## 8. Limitations and next steps
Limitations: unvalidated vision accuracy, untuned weights, synthetic history and demo drains, no live rainfall,
in-memory storage, no authentication. Next steps: labelled image set and evaluation (`docs/evaluation-plan.md`), a
rainfall data source, real maintenance/flood history, a field pilot with a maintenance team, persistence and auth.
