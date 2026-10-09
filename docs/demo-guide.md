# Demo guide

About 7 minutes. Everything uses real local inference except what is explicitly labelled synthetic or mock.
The model can return a different percentage on different runs: show whatever it returns and explain it.

## Before you go on stage (10 minutes earlier)

```powershell
ollama list
```
`gemma3:12b` must be listed. Then start the app:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

1. Open <http://127.0.0.1:8000/>. The header must say **Backend connected**.
2. Warm the model: analyse the blocked sample once (the first call loads the model and is slower).
3. Restart the server if you want a clean queue (uploads and trend history are in memory).
4. Check internet for the map (Leaflet and tiles). Without it the queue, KPIs and analysis still work.
5. Keep `docs/judge-qa.md` open for questions. Use a laptop screen of 1280 px or wider for the three-column layout.

## Live order

1. **Problem and user (40 s).** Maintenance crews cannot inspect every drain before heavy rain; the question is *which
   drain first, and why*. The tool turns a drain photo into an explained inspection priority. (Use only facts from the
   official problem statement.)
2. **Command-centre overview (40 s).** Point at the KPI strip (counts from the drain records; Critical, High and Needs
   inspection are tinted when non-zero), the map (risk-coloured markers, dashed ring = synthetic demo location) and the
   **inspection queue** on the right. Say plainly that the 7 starting records are synthetic demo data.
3. **Real blocked-drain upload (40 s).** In *Analyse a drain image*: *Try a sample → Blocked drain*, Drain ID `DEMO-1`,
   open *Location and rainfall*, click the map to set the location, rainfall `90`, *Run analysis*. The button shows a
   spinner and cannot be clicked twice.
4. **The model's visual assessment (40 s).** In *Analysis details*: "Real image analysis (local model)", the blockage
   estimate labelled *rough visual estimate, not a measurement*, *Model confidence: not provided*, and the
   "Assessed by" line naming the local model.
5. **Risk score and factors (40 s).** The score bar and level, contributing factors (blockage, rainfall
   operator-supplied, history unavailable), and the caption *not a probability of flooding*.
6. **Alert and action (30 s).** The banner appears **only because the backend triggered it** (HIGH or CRITICAL), with the
   recommended action. The new marker (selected, dark ring), the queue entry and the KPIs all show the same level.
7. **Inconclusive path (45 s).** *Try a sample → Clear drain*, ID `DEMO-2`, *Run analysis*. In our runs the model said
   the opening was not clearly visible, so the result was inconclusive: grey badge, no score, the previous alert
   cleared, the reasons listed, and "not evidence that the drain is clear". If the model returns something else, say so
   and explain the rule: no usable estimate means no score and no alert.
8. **Inspection queue (30 s).** DEMO-2 sits in *Needs manual inspection*, above Schedule/Routine, so unknown risk is not
   buried. Each row shows the recommended action and flags (analysed image, synthetic history, assumed rainfall…).
   Clicking a row or a marker opens the same detail.
9. **What-if simulator (50 s).** Click `DEMO-1` in the queue. In the violet **HYPOTHETICAL** panel set blockage to 20%
   and rainfall to 10 mm/day, *Run scenario*. Show baseline vs hypothetical, the score and category change and the
   changed inputs. The real result and its alert are unchanged: same engine, no alert, nothing stored.
10. **Limitations (40 s).** No accuracy study yet (`docs/evaluation-plan.md`), weights are design choices, history and
    demo drains are synthetic, no live rainfall, in-memory prototype. It avoids misleading output by refusing to score
    unclear images, labelling every assumption, and keeping hypothetical values separate from real ones.

## Optional: error handling (20 s)
Upload a non-image file renamed to `.jpg`: `INVALID_INPUT` with a clear message and a Retry button. If Ollama is
stopped, the result is `VISION_SERVICE_ERROR`, never a "clear" drain.

## Fallbacks

| Problem | Do this |
|---|---|
| Model slow (first call) | Talk through the overview while it runs; the button shows progress. |
| Ollama down | Error panel with Retry. Run `ollama serve`, then Retry. If it cannot be fixed, open `/?mock=1` and **say it is mock data** ("Mock data" badge, `[MOCK]` alerts). |
| No internet | Analysis, KPIs and queue still work; the map shows a notice if tiles cannot load. |
| Backend restarted mid-demo | The page notices within ~15 s, reconnects and reloads the queue; earlier uploads are gone. |

## Claims to avoid
No accuracy or precision numbers, no "predicts floods", no "live rainfall", no "real city data", no claims of deployment
or partners. The two samples are examples, not an evaluation set; the smoke test checks the software, not accuracy.
