# Drain Image Analysis

This is an **experimental local vision-language-model baseline** for the AI Urban Flood Sentinel hackathon. It sends an image to a vision-capable model served by Ollama and asks for a conservative, structured visual assessment of whether visible material appears to obstruct a drain opening.

It is not a trained drain-blockage detector and is not validated for operational/public-safety decisions. The model's self-reported confidence is not calibrated, so the component returns `confidence: null`. A blockage percentage is returned only when the model reports a visible drain and a non-uncertain positive blockage estimate; it remains a rough visual estimate, not a measurement.

## Requirements

- Python 3.10 or newer
- Ollama running locally
- A vision-capable model installed in Ollama; the default is `gemma3:12b`

Check models with:

```powershell
ollama list
```

If `gemma3:12b` is not present and downloading is permitted/time allows, install it with `ollama pull gemma3:12b`. Avoid downloading it during a time-critical demo if it is already available under another name; pass that installed model name to `analyze_drain` instead.

No Python third-party packages are required. The module uses Python's standard library and Ollama's local HTTP API.

## Usage

From the repository root:

```python
from vision import analyze_drain

result = analyze_drain(
    r"data\drain_sample.jpg",
    drain_id="DRAIN-001",
    location={"lat": 12.9716, "lon": 77.5946},
)
print(result)
```

The image may be a path, `bytes`/`bytearray`, or a binary file object. The function defaults to `http://127.0.0.1:11434` and `gemma3:12b`; both can be overridden. It accepts common PNG, JPEG, WebP, GIF, and BMP signatures and rejects empty files, unknown formats, and images exceeding 10 MiB by default.

## Output

A successful call returns a dictionary with:

- `drain_id`: supplied ID, or `null`
- `blockage_detected`: boolean representing a positive visible assessment
- `blockage_percentage`: rough 0–100 visual estimate, or `null`
- `confidence`: always `null` (no calibrated confidence is available)
- `location`: supplied `{"lat": ..., "lon": ...}` or `null`
- `timestamp`: UTC ISO-8601 timestamp
- `method`: model/method description
- `warnings`: limitation and uncertainty messages

If the image is invalid, `VisionInputError` is raised. If Ollama is unreachable, the model is missing, or the response cannot be validated, `VisionServiceError` is raised. The backend should catch these and return a controlled component error rather than treating the drain as clear.

## Tests

From repository root:

```powershell
python -m unittest discover -s tests -v
```

The unit tests mock Ollama responses, so they do not require the model server. They verify input validation and output handling, not real-world detection accuracy.

## Limitations

- A general vision-language model can miss small obstructions or infer objects incorrectly.
- Lighting, water reflections, camera angle, occlusion, and drain design affect the result.
- The percentage is an uncalibrated visual estimate, not a geometric measurement.
- `confidence` is always `null`; generated confidence scores are not accepted as calibration.
- A negative result, especially with warnings, does not establish that a drain is clear.
- Validate on permitted, labelled images before presenting any performance claims. Do not call this a flood predictor; the downstream risk engine is a separate component.
