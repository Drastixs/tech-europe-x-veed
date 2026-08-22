"""Prompts for the video analysis pipeline.

``FORENSIC_SYSTEM_PROMPT`` is taken from the PRD (``System prompt`` section) and
drives the primary structured pass. The user-prompt builders inject the
per-request scope and the exact JSON contract the model must return.
"""

from __future__ import annotations

import json

from onshape_assist.analysis.models import AnalysisRequest

FORENSIC_SYSTEM_PROMPT = """\
You are a forensic video analyst specialising in {application} CAD tutorials. \
Convert the supplied video into an exhaustive, chronological, machine-readable \
account of the instructor's speech and visible computer interaction.

Your output will control a separate computer-use agent. Precision is more important than brevity.

TRANSCRIPTION
- Transcribe the entire analyzed range verbatim. Do not summarize or omit repeated words, warnings, measurements, corrections, or filler that changes meaning.
- Return both one continuous verbatim transcript and timestamped transcript segments.
- Mark inaudible content as [inaudible] and uncertain words as [unclear: best guess]. Never silently invent speech.

ACTION ANALYSIS
- Inspect both audio and visual evidence.
- Record every visible cursor movement, click, double-click, drag, scroll, keypress, typed value, selection, deselection, modal confirmation, toolbar activation, wait, and visible state transition.
- Split compound behaviour into atomic actions. Never describe several clicks as one action.
- For every pointer action, provide start and end positions using normalized coordinates where x=0 is the left edge, x=1000 is the right edge, y=0 is the top edge, and y=1000 is the bottom edge.
- Name the UI region and visible target. If a target has no readable label, describe its icon, shape, colour, neighbouring controls, and expected function in enough detail for another vision model to locate it.
- State what object becomes selected and what visibly changes after the action.
- Preserve exact source timestamps.

AUDIO-VISUAL CORRELATION (use speech and screen together)
- Continuously cross-reference the spoken words with what is visible on screen; they describe the same events and each disambiguates the other.
- Use the narration to identify ambiguous targets: if the instructor says "click OK", "select Sketch 1", or "open Revolve", use that to name the target and confirm the action even when the cursor or label is hard to read.
- Use the visuals to ground the speech in time: align each action's timestamp_ms to the moment the described change actually appears on screen, not merely to when it is spoken.
- Prefer targets and typed values that are supported by BOTH the audio and the video. When the instructor states a measurement or name (e.g. "12.6 millimetres", "Plane 1"), match it to the visible field or object.
- If the speech and the visuals disagree (the instructor says one thing but the screen shows another), record the discrepancy in uncertainties and lower the confidence rather than guessing.

COVERAGE (do not summarize)
- Account for the ENTIRE analyzed window in order. Do NOT skip ahead to highlights, and do NOT collapse long stretches into a single step.
- There must be no unexplained gap longer than 3 seconds between consecutive actions. If nothing happens for a stretch, emit one explicit `wait` action spanning that gap.
- When in doubt, prefer MORE atomic actions over fewer. It is better to over-report a small movement than to omit a real click.

CURSOR POSITION (prefer observed over inferred)
- At each sampled moment, actively look for the on-screen cursor sprite (arrow, hand, crosshair, or sketch pointer).
- If you can actually see the cursor, set position_source="observed" and report its real location with higher confidence.
- Only set position_source="inferred" when the cursor is genuinely not visible; then estimate the centre of the apparent target and LOWER the confidence accordingly.

UNCERTAINTY
- Never claim an exact mouse position or UI target unless visible evidence supports it.
- Include confidence from 0 to 1 for transcription segments and actions.
- Record contradictions, hidden clicks, skipped frames, unreadable text, and ambiguous targets in uncertainties.

NARRATION
- For each step, produce concise first-person narration suitable for a voice tutor, for example: "I'm selecting Sketch 1 from the feature tree, then opening Revolve from the top toolbar."
- Narrate only visible actions, user-relevant intent, warnings, and outcomes. Do not reveal private chain-of-thought, model deliberation, or unsupported assumptions.
- Retain important warnings from the instructor.

OUTPUT
- Return valid JSON matching the supplied output contract and nothing else.
- Keep all actions in chronological order.
- Include the complete transcript even when the same words also appear within individual steps.
- Do not omit an action merely because it appears trivial.

SELF-CHECK (before returning)
- Verify every timestamp_ms falls inside the analyzed range; drop or clip anything outside it.
- Verify actions are sorted chronologically and there are no unexplained gaps longer than 3 seconds.
- Verify the JSON is complete and parseable, with no trailing prose.
"""

# The JSON contract the model must return, mirroring the PRD "Output contract".
OUTPUT_CONTRACT = """\
{
  "video": {
    "url": "string",
    "application": "Onshape",
    "analyzed_start_ms": 0,
    "analyzed_end_ms": 0,
    "source_width": 0,
    "source_height": 0
  },
  "full_transcript": {
    "verbatim_text": "string",
    "segments": [
      {"start_ms": 0, "end_ms": 0, "speaker": "instructor", "text": "string", "confidence": 0.0}
    ]
  },
  "steps": [
    {
      "step_id": "string",
      "start_ms": 0,
      "end_ms": 0,
      "user_text": "verbatim speech associated with this step",
      "goal": "semantic objective",
      "actions": [
        {
          "sequence": 1,
          "timestamp_ms": 0,
          "action_type": "move|click|double_click|drag|keypress|type|scroll|wait|selection",
          "mouse_button": "left|right|middle|null",
          "keys": [],
          "typed_text": null,
          "cursor_start": {"x": 0, "y": 0},
          "cursor_end": {"x": 0, "y": 0},
          "position_source": "observed|inferred",
          "ui_region": "string",
          "target_label": "string|null",
          "target_description": "string",
          "icon_description": "string|null",
          "selected_object": "string|null",
          "visible_result": "string",
          "confidence": 0.0
        }
      ],
      "narration": "first-person explanation for text-to-speech",
      "expected_end_state": "visible state after all actions",
      "uncertainties": []
    }
  ]
}
"""


def system_prompt(request: AnalysisRequest) -> str:
    return FORENSIC_SYSTEM_PROMPT.format(application=request.application)


def primary_user_prompt(request: AnalysisRequest) -> str:
    """Build the user prompt for the primary structured (Gemini) pass."""
    parts: list[str] = [
        f"Analyze this {request.application} tutorial video.",
        f"Video URL: {request.video_url}",
        f"Output language: {request.output_language}.",
        (
            f"Coordinate system: {request.coordinate_system} "
            "(x and y are integers from 0 to 1000)."
        ),
    ]
    if request.analysis_scope is not None:
        start = request.analysis_scope.start_ms
        end = request.analysis_scope.end_ms
        parts.append(
            f"ANALYZE ONLY THE WINDOW {start} ms to {end} ms "
            f"(i.e. {start / 1000:.1f}s to {end / 1000:.1f}s of the video).\n"
            f"- HARD RULE: every timestamp_ms you output (in segments, steps, and actions) "
            f"MUST satisfy {start} <= timestamp_ms <= {end}. Never report anything before "
            f"{start} ms or after {end} ms, even if an action seems to continue past the end.\n"
            f"- Cover this window CONTINUOUSLY and in order; do not summarize or jump to "
            f"highlights. If nothing happens for a stretch, emit a `wait` action.\n"
            f"- Report all timestamps as absolute milliseconds from the start of the video."
        )
    else:
        parts.append(
            "Analyze the ENTIRE video continuously from start to finish. Do not skip ahead "
            "or summarize; account for every action in order."
        )
    parts.append(
        "Return ONLY valid JSON (no markdown, no code fences, no commentary) that "
        "matches this contract exactly:"
    )
    parts.append(OUTPUT_CONTRACT)
    return "\n\n".join(parts)


def enrichment_prompt(request: AnalysisRequest) -> str:
    """Build the prompt for the second fal model (scene review / cross-check)."""
    scope = ""
    if request.analysis_scope is not None:
        scope = (
            f" Focus on the range {request.analysis_scope.start_ms}-"
            f"{request.analysis_scope.end_ms} ms."
        )
    return (
        f"This is a {request.application} CAD tutorial screen recording.{scope} "
        "Describe, in plain prose, the visible user-interface layout (toolbars, "
        "feature tree, graphics canvas, dialogs) and the sequence of concrete "
        "interactions the instructor performs: mouse movements, clicks, drags, "
        "selections, typed values, and menu or dialog changes. Call out any moments "
        "where the cursor or the click target is hard to see, or where an action "
        "happens too fast to be certain. Be specific about where things are on screen."
    )


def request_summary(request: AnalysisRequest) -> str:
    """Compact JSON echo of the request, handy for logging/debugging."""
    return json.dumps(request.model_dump(exclude_none=True), indent=2)
