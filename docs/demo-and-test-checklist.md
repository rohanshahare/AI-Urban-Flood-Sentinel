# Demo and Test Checklist

- [ ] Project starts using documented commands.
- [ ] A valid drain image can be analyzed.
- [ ] Potential blockage is handled appropriately.
- [ ] Severity is reported only when supported.
- [ ] Invalid images produce a controlled error.
- [ ] Uncertain results are disclosed.
- [ ] The vision output matches the agreed API contract.
- [ ] The backend and frontend complete an end-to-end demo.
- [ ] Synthetic or unavailable data is clearly identified.

## Verified status (see README "Test it" and docs/demo-guide.md)

- Automated: `python -m unittest discover -t . -s . -v` and `node --test tests/js/*.test.mjs`.
- Real model: `python scripts/vision_smoke_test.py` (requires Ollama + `gemma3:12b`).
- Manual: upload the blocked and clear samples through the dashboard; check completed / inconclusive / error
  states, the alert banner, map markers, KPIs and the what-if simulator.
