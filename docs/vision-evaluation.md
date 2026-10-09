# Vision Component — Initial Test Evidence

**Project:** AI Urban Flood Sentinel  
**Component:** `vision/`  
**Status:** Initial functional checks; not a validated detection model.

## Method

The component sends a permitted sample image to the locally running Ollama multimodal model (`gemma3:12b` by default) and asks for a conservative structured visual assessment. This is a qualitative vision-language-model baseline, not a model trained specifically on a drain-blockage dataset. It does not produce calibrated confidence, so `confidence` is `null`.

## Automated unit tests

Command:

```powershell
python -m unittest discover -s tests -v
```

Recorded result: **11 tests passed**. The tests cover input validation, supported input forms, output contract behavior, uncertain/no-visible-drain handling, invalid percentage handling, and a simulated Ollama service failure. The unit tests mock the Ollama response, so they are not an evaluation of real-world detection accuracy.

## Initial real-image smoke tests

These were run locally against the Ollama model on the two sample images included in the repository.

| Sample | Observed result | Interpretation |
|---|---|---|
| `data/blocked_drain.jpg` | `blockage_detected: true`, `blockage_percentage: 75.0`, `confidence: null` | Model gave a positive qualitative assessment and a rough 75% visual estimate. The percentage is not a measurement or calibrated severity. |
| `data/clear_drain.jpg` | `blockage_detected: false`, `blockage_percentage: null`, `confidence: null`; warnings stated poor image quality and that the drain opening was not clearly visible | The assessment was uncertain. This is **not proof that the drain is clear** and should remain visibly uncertain in the UI. |

These are two example runs only. They are not enough to calculate accuracy, precision, recall, or false-positive/false-negative rates. General-purpose vision-language models can miss obstructions or infer them incorrectly.

## Repeat the checks

From the repository root, with Ollama running and `gemma3:12b` installed:

```powershell
python scripts/vision_smoke_test.py
```

To check different files or select another installed model:

```powershell
python scripts/vision_smoke_test.py --images data/blocked_drain.jpg data/clear_drain.jpg --model gemma3:12b
```

The script checks that inference returns the expected machine-readable fields and types. It does **not** assert that the model must classify either image a particular way; model output can vary, and these samples are not a labelled evaluation set.

## Known limitations and judge-safe claims

- `blockage_percentage` is a rough visual estimate, not a pixel-accurate or physical measurement.
- `confidence` is unavailable (`null`) because no calibrated confidence value is produced.
- A negative result with uncertainty or visibility warnings does not mean the drain is clear.
- Image lighting, angle, occlusion, reflections, and drain design may affect results.
- The current input check recognizes common image file signatures but does not fully decode the image before sending it to Ollama.
- Do not claim validated city-wide accuracy or exact flood prediction. Position this component as visual maintenance triage that can contribute evidence to a separate downstream risk engine.
