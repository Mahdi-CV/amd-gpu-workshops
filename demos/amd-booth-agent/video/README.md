# AMD Booth Agent — 60-second teaser

This directory contains a silent-first, deterministic 60-second teaser for the
AMD OpenClaw + vLLM Semantic Router live booth demo.

## Deliverables

- `amd-booth-teaser.mp4` — rendered 1920×1080 H.264/AAC booth loop.
- `poster.jpg` — frame from the final mixture-of-models message.
- `STORYBOARD.md` — exact timeline, on-screen copy, optional voiceover, and
  cost-estimate scope.
- `teaser.html` — self-contained animation source. It references the exact AMD
  PNG assets in `../control/static/`; it does not redraw or replace them.
- `render.sh` — one-command deterministic Chrome-to-frames-to-ffmpeg render.
- `render_frames.py` — Chrome DevTools frame capture.
- `validate_video.py` — duration, dimensions, codec, frame-rate, audio, and
  decode validation.

## Render

From this directory:

```bash
./render.sh
```

The script uses tools already available on the booth workstation:

- Google Chrome or Chromium;
- Python 3 with the `websockets` module;
- ffmpeg and ffprobe.

Defaults are 1920×1080, 30 fps, exactly 60 seconds, H.264 High Profile,
`yuv420p`, and silent stereo AAC for broad playback compatibility. Temporary
frames stay under `video/.render/` and are removed after a successful render.

Useful options:

```bash
# Keep captured frames for inspection.
KEEP_FRAMES=1 ./render.sh

# Mux a finished voiceover instead of the silent audio bed.
VOICEOVER_AUDIO=/absolute/path/to/voiceover.wav ./render.sh

# Write to another path under this directory.
./render.sh ./amd-booth-teaser-alt.mp4
```

The HTML also plays directly in a browser and loops every 60 seconds:

```bash
google-chrome teaser.html
```

## Validate

`render.sh` validates automatically. To validate an existing render:

```bash
./validate_video.py amd-booth-teaser.mp4 --decode
```

The cost comparison shown in the teaser is an illustrative same-token estimate
using the model rates configured in the demo. It is not a benchmark or a claim
about a completed live run. Cloud API/token estimates exclude local AMD
Instinct hardware, hosting, power, and operating costs.
