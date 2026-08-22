from __future__ import annotations

from html import escape
from pathlib import Path


def render_launcher_page(extension_dir: Path) -> str:
    extension_path = escape(str(extension_dir))
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Onshape Assist is ready</title>
    <style>
      :root {{
        color-scheme: dark;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
        background: oklch(13% 0.014 246);
        color: oklch(93% 0.009 238);
      }}
      * {{ box-sizing: border-box; }}
      body {{
        min-height: 100vh;
        margin: 0;
        display: grid;
        place-items: center;
        padding: 32px;
        background:
          radial-gradient(circle at 18% 12%, oklch(76% 0.12 194 / 10%), transparent 32rem),
          oklch(13% 0.014 246);
      }}
      main {{ width: min(100%, 660px); }}
      .status {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 22px;
        color: oklch(79% 0.13 166);
        font-size: 13px;
        font-weight: 650;
      }}
      .status span {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: currentColor;
        box-shadow: 0 0 12px oklch(79% 0.13 166 / 48%);
      }}
      h1 {{ margin: 0 0 12px; font-size: 44px; line-height: 1.04; letter-spacing: -0.035em; }}
      .intro {{ max-width: 58ch; margin: 0 0 34px; color: oklch(70% 0.024 238); font-size: 16px; line-height: 1.6; }}
      ol {{ margin: 0; padding: 0; list-style: none; counter-reset: steps; }}
      li {{
        display: grid;
        grid-template-columns: 32px minmax(0, 1fr);
        gap: 14px;
        padding: 19px 0;
        border-top: 1px solid oklch(72% 0.025 238 / 15%);
        counter-increment: steps;
      }}
      li::before {{
        content: counter(steps);
        display: grid;
        width: 28px;
        height: 28px;
        place-items: center;
        border-radius: 9px;
        background: oklch(75% 0.12 194 / 12%);
        color: oklch(80% 0.13 194);
        font-size: 12px;
        font-weight: 720;
      }}
      h2 {{ margin: 2px 0 6px; font-size: 15px; }}
      li p {{ margin: 0; color: oklch(66% 0.024 238); font-size: 13px; line-height: 1.55; }}
      code {{
        display: block;
        margin-top: 9px;
        padding: 10px 12px;
        overflow-wrap: anywhere;
        border: 1px solid oklch(72% 0.03 238 / 18%);
        border-radius: 9px;
        background: oklch(17% 0.017 246);
        color: oklch(84% 0.06 194);
        font-size: 12px;
        user-select: all;
      }}
      .actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 30px; }}
      a {{
        display: inline-flex;
        min-height: 42px;
        align-items: center;
        justify-content: center;
        padding: 0 16px;
        border: 1px solid oklch(72% 0.03 238 / 22%);
        border-radius: 10px;
        color: oklch(88% 0.012 238);
        font-size: 13px;
        font-weight: 670;
        text-decoration: none;
      }}
      a.primary {{ border-color: transparent; background: oklch(75% 0.13 194); color: oklch(17% 0.025 214); }}
      a:focus-visible {{ outline: 3px solid oklch(76% 0.13 194 / 30%); outline-offset: 3px; }}
      @media (max-width: 520px) {{
        body {{ padding: 24px; }}
        h1 {{ font-size: 34px; }}
      }}
    </style>
  </head>
  <body>
    <main>
      <div class="status"><span aria-hidden="true"></span>Local server online</div>
      <h1>Onshape Assist is ready.</h1>
      <p class="intro">The extension is built and the tutorial relay is running. Chromium development builds load it automatically. Chrome stable needs one confirmation in its Extensions page.</p>
      <ol>
        <li>
          <div>
            <h2>Confirm the extension</h2>
            <p>If Chrome opened its Extensions page, enable Developer mode, choose Load unpacked, and select this folder:</p>
            <code>{extension_path}</code>
          </div>
        </li>
        <li>
          <div>
            <h2>Open your workspace</h2>
            <p>Open an Onshape document, then select Onshape Assist from the browser toolbar to paste a tutorial URL.</p>
          </div>
        </li>
      </ol>
      <div class="actions">
        <a class="primary" href="https://cad.onshape.com/documents">Open Onshape</a>
        <a href="/docs">View server API</a>
      </div>
    </main>
  </body>
</html>"""
