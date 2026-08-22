# PRD: Video Analysis and Narration

## Objective

Convert an Onshape tutorial video into a complete, timestamped record of:

- Everything the instructor says.
- Every visible mouse movement, click, drag, keyboard input, selection, and modal interaction.
- The visible UI target, including its label, location, and icon description.
- Narration suitable for a voice agent to speak while reproducing the tutorial step.

The resulting analysis becomes the input to the computer-use and browser-state systems. The analyzer describes actions; it does not execute them.

## User story

As an Onshape learner, I want a tutorial converted into small, exact actions so an in-browser agent can demonstrate each action and explain what it is doing without requiring me to switch between the video and Onshape.

## Inputs

```json
{
  "video_url": "https://www.youtube.com/watch?v=wSBLOhIFz6s",
  "application": "Onshape",
  "analysis_scope": {
    "start_ms": 259000,
    "end_ms": 273000
  },
  "coordinate_system": "normalized_0_to_1000",
  "output_language": "en"
}
```

`analysis_scope` is optional. Omit it to analyze the entire video.

## Test videos

Use these simple Onshape tutorials from the Maker's Muse channel as the initial analysis test set. Test a short range first, then run the full video once timestamp, transcript, and action accuracy are acceptable.

| Role | Tutorial | Duration | Test focus |
| --- | --- | ---: | --- |
| Primary example | [How to CAD your own Maker Coins in Onshape](https://www.youtube.com/watch?v=wSBLOhIFz6s) | 16:12 | Baseline sketch, selection, and revolve workflow. |
| Additional example 1 | [Designing a 3D Printer Torture Test in Onshape - 2015](https://www.youtube.com/watch?v=BFxT9CvbHu8) | 3:39 | Short end-to-end test with a small number of modelling actions. |
| Additional example 2 | [Let's Design Something in Onshape! Redbull Drink Holder - 2015](https://www.youtube.com/watch?v=KHmjRvU_nP0) | 16:02 | Tests a simple part build with repeated sketch and feature operations. |
| Additional example 3 | [Practical 3D Printing using Onshape and the Fabrikator Mini](https://www.youtube.com/watch?v=X21fkHiF1cY) | 16:42 | Tests a practical modelling workflow from design intent through a printable part. |

For every video, verify that the output contains a complete timestamped transcript, chronologically ordered atomic actions, cursor coordinates and UI targets for pointer actions, visible results, uncertainty markers where evidence is unclear, and narration that matches the demonstrated action.

## Functional requirements

1. Produce a verbatim transcript of the entire analyzed range, including timestamps and meaningful pauses or unclear words.
2. Split the video into atomic actions. One click, keypress, selection, drag, or modal confirmation equals one action.
3. Record the cursor position at the beginning and end of each action using normalized `x` and `y` coordinates from 0 to 1000.
4. Identify the UI region and target, such as the top toolbar, graphics canvas, feature tree, or sketch modal.
5. Describe unlabeled icons by shape, colour, nearby controls, and apparent purpose.
6. Record visible keyboard keys, typed values, mouse button, click count, drag path, selected object, and resulting UI change.
7. Preserve uncertainty. If the cursor or exact target is obscured, return an estimate, mark it as inferred, and lower confidence rather than inventing precision.
8. Generate short first-person narration describing the visible action and its purpose. Do not expose hidden model reasoning.
9. Maintain chronological order and retain the source timestamps required to replay or re-check the video.

## Output contract

```json
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
      {
        "start_ms": 0,
        "end_ms": 0,
        "speaker": "instructor",
        "text": "string",
        "confidence": 0.0
      }
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
          "cursor_start": { "x": 0, "y": 0 },
          "cursor_end": { "x": 0, "y": 0 },
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
```

## System prompt

```text
You are a forensic video analyst specialising in Onshape CAD tutorials. Convert the supplied video into an exhaustive, chronological, machine-readable account of the instructor's speech and visible computer interaction.

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

UNCERTAINTY
- Never claim an exact mouse position or UI target unless visible evidence supports it.
- Use position_source="observed" when the cursor is visible and "inferred" when estimating the centre of the apparent target.
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
```

## Example expected output

The following example is based on the user-supplied description of `04:19–04:33`; coordinates and visual details are illustrative until verified from decoded frames.

```json
{
  "video": {
    "url": "https://www.youtube.com/watch?v=wSBLOhIFz6s",
    "application": "Onshape",
    "analyzed_start_ms": 259000,
    "analyzed_end_ms": 273000,
    "source_width": 1920,
    "source_height": 1080
  },
  "full_transcript": {
    "verbatim_text": "Make sure no straight lines in the sketch. This will stop the revolve from forming.",
    "segments": [
      {
        "start_ms": 259000,
        "end_ms": 264500,
        "speaker": "instructor",
        "text": "Make sure no straight lines in the sketch. This will stop the revolve from forming.",
        "confidence": 0.92
      }
    ]
  },
  "steps": [
    {
      "step_id": "confirm-sketch-and-open-revolve",
      "start_ms": 259000,
      "end_ms": 273000,
      "user_text": "Make sure no straight lines in the sketch. This will stop the revolve from forming.",
      "goal": "Finish the current sketch, select Sketch 1, and open the Revolve feature.",
      "actions": [
        {
          "sequence": 1,
          "timestamp_ms": 264600,
          "action_type": "click",
          "mouse_button": "left",
          "keys": [],
          "typed_text": null,
          "cursor_start": { "x": 812, "y": 731 },
          "cursor_end": { "x": 812, "y": 731 },
          "position_source": "inferred",
          "ui_region": "active sketch modal",
          "target_label": "OK",
          "target_description": "The confirmation button in the current sketch modal.",
          "icon_description": null,
          "selected_object": null,
          "visible_result": "The sketch modal closes and the completed sketch appears in the feature tree.",
          "confidence": 0.55
        },
        {
          "sequence": 2,
          "timestamp_ms": 267500,
          "action_type": "click",
          "mouse_button": "left",
          "keys": [],
          "typed_text": null,
          "cursor_start": { "x": 91, "y": 292 },
          "cursor_end": { "x": 91, "y": 292 },
          "position_source": "inferred",
          "ui_region": "left feature tree",
          "target_label": "Sketch 1",
          "target_description": "The newly created Sketch 1 entry in the left feature tree.",
          "icon_description": "A small sketch-feature icon immediately before the Sketch 1 label.",
          "selected_object": "Sketch 1",
          "visible_result": "Sketch 1 becomes highlighted as the active selection.",
          "confidence": 0.55
        },
        {
          "sequence": 3,
          "timestamp_ms": 270800,
          "action_type": "move",
          "mouse_button": null,
          "keys": [],
          "typed_text": null,
          "cursor_start": { "x": 91, "y": 292 },
          "cursor_end": { "x": 358, "y": 62 },
          "position_source": "inferred",
          "ui_region": "top feature toolbar",
          "target_label": "Revolve",
          "target_description": "The Revolve tool in the top feature toolbar.",
          "icon_description": "A profile or curved shape rotating around a vertical axis, positioned among the solid-feature tools.",
          "selected_object": "Sketch 1",
          "visible_result": "The cursor rests over the Revolve tool.",
          "confidence": 0.45
        },
        {
          "sequence": 4,
          "timestamp_ms": 271300,
          "action_type": "click",
          "mouse_button": "left",
          "keys": [],
          "typed_text": null,
          "cursor_start": { "x": 358, "y": 62 },
          "cursor_end": { "x": 358, "y": 62 },
          "position_source": "inferred",
          "ui_region": "top feature toolbar",
          "target_label": "Revolve",
          "target_description": "The Revolve tool selected after Sketch 1 is highlighted.",
          "icon_description": "A profile or curved shape rotating around a vertical axis.",
          "selected_object": "Sketch 1",
          "visible_result": "The Revolve feature dialog opens for Sketch 1.",
          "confidence": 0.45
        }
      ],
      "narration": "Make sure the sketch contains no unwanted straight lines, because they can prevent the revolve from forming. I'm confirming the sketch, selecting Sketch 1 from the feature tree, and opening Revolve from the top toolbar.",
      "expected_end_state": "Sketch 1 is selected and the Revolve feature dialog is open.",
      "uncertainties": [
        "Coordinates and icon appearance require verification from the source frames.",
        "The supplied spoken wording may differ slightly from the video's exact audio."
      ]
    }
  ]
}
```

## Acceptance criteria

- The continuous transcript covers 100% of the analyzed range.
- Every visible interaction is represented as an atomic action.
- Every pointer action has coordinates, provenance, and confidence.
- Every unlabeled control has a usable visual description.
- Important warnings and measurements appear in both the transcript and relevant step.
- Narration is synchronized to steps and contains no hidden reasoning.
- Output validates against the JSON contract.

## Constraints

- A model that samples video at roughly one frame per second may miss fast actions. Low-confidence segments should be reprocessed from shorter clips or higher-frequency extracted frames.
- Exact coordinates depend on the source resolution and must be localized again against the user's live Onshape viewport before execution.
- The example above is a specification example based on user-provided content, not a verified transcription of the linked video.
