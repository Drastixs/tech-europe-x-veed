# Onshape Assist

A Chromium MV3 extension that places a click-through assistive overlay and independent virtual cursor over Onshape. A small local FastAPI relay lets a terminal command drive the demonstration without moving or hiding the user's real cursor.

## Run the demo

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

## Test one real computer-use action

With the extension connected to an active Onshape document, post one typed action:

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
