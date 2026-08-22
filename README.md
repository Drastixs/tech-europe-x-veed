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

## Checks

```bash
npm run check
npm run build
```

The extension is deliberately scoped to `https://cad.onshape.com/*`. The local relay is hackathon boilerplate, not a production authentication or durable job system.
