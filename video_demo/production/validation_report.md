# Final render validation

- Output: `video_demo/AI_Urban_Flood_Sentinel_Demo.mp4` (73,469,154 bytes)
- Duration: exactly 150.000 seconds; 1920 × 1080, H.264, 30 fps, 4,500 frames.
- Audio: AAC mono, 96 kHz; narration is 149.4 seconds with a 0.6-second closing hold. Measured mean level: -16.3 dBFS; peak: -1.2 dBFS.
- Captions: 77 short phrase cues burned into the video and also supplied as `video_demo/captions.srt`. Final cue ends at 149.4 seconds; cues do not overlap.
- Footage: real browser recording of the dashboard, with eased camera moves across nine timed shots and 0.35-second transitions. Inspected a contact sheet and full-resolution frames across opening, dashboard, analysis, queue, fixture examples, and closing card. No black frames were detected.
- Speech: paragraph-specific Microsoft Zira Desktop speech synthesized locally. Captions derive from speech progress events and are scaled to each paragraph's WAV duration. Loudness/peak were measured, but no perceptual listening test was available; naturalness is therefore not claimed as independently verified.
- Data integrity: the recorded dashboard is visibly in mock mode. Fixture outputs, history, and sample records are synthetic; the narration states that no image is analyzed in this recording and does not present the fixtures as live model results.
- Reference: the requested Guru Graph reference video was not found among accessible project assets, so this render follows the written style direction rather than claiming a direct visual comparison.
- Runtime note: Ollama was unavailable during capture. `MOCK DATA` remains visible, and the real model pipeline is described conditionally rather than presented as active.
