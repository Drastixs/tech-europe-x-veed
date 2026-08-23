# Onshape Assist

A Chromium MV3 extension that places a click-through assistive overlay and independent virtual cursor over Onshape. A small local FastAPI relay lets a terminal command drive the demonstration without moving or hiding the user's real cursor.

## Run the demo

### Prerequisites

- Node.js 22 and npm
- Python 3.11 or newer with [uv](https://docs.astral.sh/uv/)
- Chromium or Chrome for the extension demo
- `FAL_KEY` for video analysis and ElevenLabs narration; `HAI_API_KEY` for live computer-use localization

The automated checks use fake provider responses and do not require either API key.

### One-command launcher

On Linux, run:

```bash
./start-onshape-assist.sh
```

The launcher installs missing project dependencies, builds the extension, starts the local
FastAPI server, and opens `http://127.0.0.1:8000`.

When Chromium or Chrome for Testing is installed, the launcher opens a dedicated browser
profile with the extension preloaded. Chrome stable removed command-line unpacked extension
loading in Chrome 137, so it opens `chrome://extensions` and shows the exact folder to select
with **Load unpacked**. Keep the launcher terminal open while using the demo, and press `Ctrl+C`
to stop the server.

Set `ONSHAPE_ASSIST_BROWSER` to a browser executable if automatic detection does not select the
browser you want.

### Manual setup

Install dependencies:

```bash
npm install
uv sync --project services/backend --extra dev
```

Start the relay:

```bash
uv run --project services/backend uvicorn onshape_assist.app:app --host 127.0.0.1 --port 8000
```

For computer-use localization, copy `.env.example` to `.env` and set `HAI_API_KEY`.

Build the extension:

```bash
npm run build
```

In Chromium, open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and select `apps/extension/output/chrome-mv3`. Then open an Onshape document.

Paste a public YouTube or video URL into the extension popup and choose **Add tutorial**. The
extension background worker keeps the request alive while the local backend runs the complete
pipeline:

```text
video URL → fal video analysis → strict analysis contract → tutorial planning
          → concise + detailed fal ElevenLabs narration → WebSocket → Onshape overlay
```

The same flow is available directly over HTTP:

```bash
curl --fail-with-body http://127.0.0.1:8000/tutorials/from-video \
  --header 'Content-Type: application/json' \
  --data '{
    "video_url": "https://www.youtube.com/watch?v=wSBLOhIFz6s",
    "tutorial_id": "maker-coin",
    "runtime_preferences": {"detailed_narration": false}
  }'
```

Drive the overlay from another terminal:

```bash
uv run --project services/backend overlayctl show
uv run --project services/backend overlayctl move 700 460
uv run --project services/backend overlayctl right
uv run --project services/backend overlayctl left
uv run --project services/backend overlayctl click
uv run --project services/backend overlayctl hide
```

`click` activates an overlay navigation button only when the virtual cursor is over it. The physical mouse cursor is never moved or hidden. Trusted physical pointer movement or pointer-down hides the virtual guidance; a new command or arrow-key step brings it back.

## Architecture and contracts

The supported runtime is a Chromium MV3 extension connected to local FastAPI
services. The extension renders guidance and never moves the user's real
pointer; the backend owns provider credentials and validates committed Onshape
state. Versioned payloads shared across both are defined in
[`contracts/runtime-v1.schema.json`](contracts/runtime-v1.schema.json). Its
canonical Revolve fixture is exercised by both test suites.

## Video analysis & tutorial extraction

Convert an Onshape tutorial video into a timestamped record of speech and visible
interaction (see [the PRD](prds/video-analytis-and-narration.md)). The pipeline mixes two
fal partner models: `openrouter/router/video` (Gemini 3.1 Pro) for the primary structured pass
(YouTube links supported) and `fal-ai/video-understanding` for an enrichment/cross-check
pass on direct media URLs.

Set your fal key (copy `services/backend/.env.example` to `services/backend/.env` and fill
in `FAL_KEY`, or `export FAL_KEY=...`). Then run the analyzer:

```bash
# Short range of a YouTube tutorial
uv run --project services/backend analyzectl \
  --video-url https://www.youtube.com/watch?v=wSBLOhIFz6s --start-ms 259000 --end-ms 273000

# From a request file matching the PRD input contract
uv run --project services/backend analyzectl \
  --input services/backend/examples/maker-coin-clip.json --output analysis.json
```

Or over HTTP once the relay is running:

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d @services/backend/examples/maker-coin-clip.json
```

The output validates against the PRD JSON contract. `POST /tutorials/from-video` passes that
validated output directly into tutorial planning and voice narration. `POST /analyze` and
`POST /tutorials/plan` remain available for testing either stage independently.

## Tutorial planning

`plannerctl` converts a planning request containing video analysis and tutorial metadata
into the live tutorial-plan protocol consumed by the extension. It uses the backend-only
OpenAI and fal credentials, and returns `tutorial-planner-error/v1` envelopes on failure.

```bash
uv run --project services/backend plannerctl \
  --input services/backend/fixtures/revolve-from-sketch-1.analysis-to-plan-v1.json \
  --output tutorial-plan.json
```

The committed fixture includes both the request and its canonical expected plan; `plannerctl`
automatically reads the fixture's `request` object.

## Test computer-use execution

To execute every action in a tutorial step, post the complete `TutorialStep` object from a
generated plan. The backend runs its actions in sequence, capturing and grounding against a fresh
screenshot before each action. It stops on the first failed action and returns the attempted action
results:

```bash
jq '{step: .steps[0], execute: true}' tutorial-plan.json | \
  curl -X POST http://127.0.0.1:8000/computer-use/demonstrate-step \
    -H 'Content-Type: application/json' --data-binary @-
```

The single-action endpoint remains available for testing. With the extension connected to an
active Onshape document, post one typed action:

```bash
curl -X POST http://127.0.0.1:8000/computer-use/demonstrate \
  -H 'Content-Type: application/json' \
  -d '{
    "step_goal": "Open Revolve",
    "execute": true,
    "action": {
      "sequence": 1,
      "action_type": "click",
      "parameters": {"button": "primary"},
      "ui_region": "left feature tree",
      "target_label": "Sketch 1",
      "target_description": "Sketch 1 in the left feature tree",
      "icon_description": "A blue sketch glyph beside the Sketch 1 label",
      "semantic_action": "Select Sketch 1",
      "expected_visible_result": "Sketch 1 is highlighted",
      "preferred_activation": "dom_js",
      "fallback_activation": "cdp"
    }
  }'
```

The backend requests a screenshot from the extension, asks Holo3 for normalized coordinates,
moves the virtual cursor, and executes the action only when the DOM element under the localized
point matches the requested label. Set `"execute": false` to test grounding without clicking.

## Checks

```bash
npm run check
npm run build
```

The extension is deliberately scoped to `https://cad.onshape.com/*`. The local relay is hackathon boilerplate, not a production authentication or durable job system.
