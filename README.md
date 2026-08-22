# Onshape Assist

A Chromium MV3 extension that places a click-through assistive overlay and independent virtual cursor over Onshape. A small local FastAPI relay lets a terminal command drive the demonstration without moving or hiding the user's real cursor.

## Run the demo

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

Build the extension:

```bash
npm run build
```

In Chromium, open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and select `apps/extension/.output/chrome-mv3`. Then open an Onshape document.

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

The output validates against the PRD JSON contract and becomes the input to the
computer-use and browser-state systems.

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

## Checks

```bash
npm run check
npm run build
```

The extension is deliberately scoped to `https://cad.onshape.com/*`. The local relay is hackathon boilerplate, not a production authentication or durable job system.
