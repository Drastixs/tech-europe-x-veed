# PRD: Tutorial Planning and Voice Narration

## Objective

Convert analyzed Onshape tutorial actions into executable, step-by-step tutorial plans with ready-to-play voice narration for each step.

This system receives the timestamped video analysis output from System 1 and produces:

- A normalized tutorial plan grouped into user-meaningful steps.
- Concise and detailed narration variants for every step.
- Voice timing cues that Section 3 can use while demonstrating the step.
- Dynamic correction narration for retries, state mismatch, or user interruption.
- JSON contracts suitable for browser execution and instant runtime narration switching.

Narration describes user-visible actions, user-relevant intent, and visible results only. It must never expose hidden chain-of-thought, private model deliberation, or internal implementation details.

## User story

As an Onshape learner, I want the assistant to explain each demonstrated action at the level of detail I prefer, so I can either follow a quick guided demo or hear the exact next clicks before they happen.

## Inputs

```json
{
  "tutorial_id": "maker-coin-revolve",
  "application": "Onshape",
  "output_language": "en",
  "voice": {
    "provider": "fal_elevenlabs",
    "voice_id": "string",
    "speaking_rate": 1.0
  },
  "runtime_preferences": {
    "detailed_narration": false
  },
  "video_analysis": {
    "video": {},
    "full_transcript": {},
    "steps": []
  }
}
```

`runtime_preferences.detailed_narration` controls which pre-generated narration variant is played:

- `false`: concise intent/result narration, for example “Let’s revolve Sketch 1.”
- `true`: step-by-step action narration, for example “Let’s revolve Sketch 1. First I’ll select Sketch 1 from the left feature tree, then I’ll click Revolve in the top toolbar.”

Both variants are generated and stored for every step so switching modes at runtime does not require a new LLM or TTS call.

## Functional requirements

1. Convert low-level analyzed actions into coherent tutorial steps with a single semantic goal.
2. Preserve action order, required UI targets, expected visible results, and uncertainty notes from System 1.
3. Generate two narration text variants per step:
   - `concise`: short intent/result narration.
   - `detailed`: preview of the specific user-visible actions.
4. Generate fal-hosted ElevenLabs TTS audio for both narration variants before runtime playback.
5. Store audio URLs or asset IDs for both variants on each step.
6. Return cue timing so Section 3 can play narration before, during, or after virtual cursor motion.
7. Include dynamic correction lines for retry, target relocation, failed validation, and user interruption.
8. Never narrate the implementation mechanism. For example, say “I’ll click Revolve,” not “I’ll dispatch a JavaScript click.”
9. Keep narration aligned with visible Onshape state and stop if the expected precondition is not met.

## Output contract

```json
{
  "tutorial_id": "string",
  "application": "Onshape",
  "output_language": "en",
  "runtime_preferences": {
    "detailed_narration": false
  },
  "voice": {
    "provider": "fal_elevenlabs",
    "voice_id": "string",
    "speaking_rate": 1.0
  },
  "steps": [
    {
      "step_id": "string",
      "goal": "semantic objective",
      "preconditions": [
        "visible state required before execution"
      ],
      "actions": [
        {
          "sequence": 1,
          "action_type": "move|click|double_click|drag|keypress|type|scroll|wait|selection",
          "parameters": "action-specific parameters from the table below",
          "ui_region": "string",
          "target_label": "string|null",
          "target_description": "string",
          "semantic_action": "user-visible action phrasing",
          "expected_visible_result": "string",
          "preferred_activation": "dom_js|cdp|vision_only",
          "fallback_activation": "cdp|null"
        }
      ],
      "narration": {
        "concise": {
          "text": "string",
          "fal_elevenlabs_audio_url": "string",
          "duration_ms": 0
        },
        "detailed": {
          "text": "string",
          "fal_elevenlabs_audio_url": "string",
          "duration_ms": 0
        }
      },
      "voice_cues": [
        {
          "cue_id": "string",
          "phase": "before_step|before_action|during_action|after_action|after_step|on_retry|on_user_interrupt",
          "action_sequence": 1,
          "variant": "concise|detailed|both",
          "text_ref": "narration.concise.text",
          "start_policy": "play_before_motion|play_with_motion|play_after_validation|play_on_event",
          "blocking": true
        }
      ],
      "dynamic_corrections": {
        "retry": "I didn’t find that in the expected place, so I’m checking the screen again.",
        "validation_failed": "That didn’t open as expected, so I’ll pause here instead of continuing.",
        "user_interrupt": "You moved the mouse, so I’ll stop the demonstration and restore the previous state."
      },
      "expected_end_state": "visible state after all actions",
      "uncertainties": []
    }
  ]
}
```

`parameters` is discriminated by `action_type`; fields from another action type are invalid.

| Action type | Required parameters |
| --- | --- |
| `move` | `duration_ms` |
| `click` | `button: primary\|secondary\|middle` |
| `double_click` | `button`, `interval_ms` |
| `drag` | `end_target_label`, `end_target_description`, `duration_ms` |
| `keypress` | `key`, `modifiers: alt\|control\|meta\|shift[]`, `repeat` |
| `type` | `text`, `clear_existing`, `submit` |
| `scroll` | non-zero `delta_x` or `delta_y`, plus `duration_ms` |
| `wait` | nullable `duration_ms` and `condition`; at least one must be set |
| `selection` | non-empty `items`, `mode: replace\|add\|toggle`, `confirm` |

## System prompt

```text
You are a tutorial planner and voice director for an Onshape in-browser teaching assistant.

You receive timestamped video-analysis JSON containing transcript, atomic actions, UI targets, visible results, coordinates, and uncertainty notes. Convert it into a clean tutorial plan that another system can demonstrate in the user's live Onshape tab.

PLANNING
- Group atomic actions into user-meaningful steps with one clear semantic goal each.
- Preserve the chronological order of actions.
- Keep target labels, UI regions, expected visible results, and uncertainty notes.
- Define preconditions and expected end state for each step.
- Use semantic action phrasing that describes what the user sees, such as "select Sketch 1" or "open Revolve."

ACTIVATION GUIDANCE
- For stable DOM targets, prefer preferred_activation="dom_js" so Section 3 can activate the target through a virtual element or JavaScript click without taking over the user's real mouse.
- For canvas, WebGL, inaccessible, or unstable targets, use preferred_activation="cdp" because browser-level input may be required.
- Always include fallback_activation="cdp" when DOM activation may fail.
- Narration must describe the semantic user-visible action, never the implementation mechanism.

VOICE
- Generate two narration variants for every step.
- concise: short intent/result narration, suitable for users who want minimal explanation.
- detailed: step-by-step narration that previews visible actions before they happen.
- Both variants must be safe to store and play instantly at runtime.
- Use fal-hosted ElevenLabs TTS metadata fields for generated audio assets.
- Narrate only visible actions, user-relevant intent, warnings, and outcomes.
- Never reveal hidden chain-of-thought, private model reasoning, raw coordinates, API choices, CDP, DOM events, or unsupported assumptions.

TIMING
- Provide voice cues that specify when narration should play relative to the virtual demonstration.
- Detailed narration usually plays before the first action.
- Concise narration may play before motion or after successful validation, depending on what sounds natural.
- Correction narration plays only on retry, validation failure, or user interruption.

OUTPUT
- Return valid JSON matching the output contract and nothing else.
- Keep wording natural, short, and appropriate for spoken audio.
```

## Example expected output

```json
{
  "tutorial_id": "maker-coin-revolve",
  "application": "Onshape",
  "output_language": "en",
  "runtime_preferences": {
    "detailed_narration": false
  },
  "voice": {
    "provider": "fal_elevenlabs",
    "voice_id": "friendly-tutor",
    "speaking_rate": 1.0
  },
  "steps": [
    {
      "step_id": "open-revolve-for-sketch-1",
      "goal": "Open the Revolve feature for Sketch 1.",
      "preconditions": [
        "Sketch 1 exists in the left feature tree.",
        "The top feature toolbar is visible."
      ],
      "actions": [
        {
          "sequence": 1,
          "action_type": "click",
          "parameters": { "button": "primary" },
          "ui_region": "left feature tree",
          "target_label": "Sketch 1",
          "target_description": "The Sketch 1 entry in the left feature tree.",
          "semantic_action": "Select Sketch 1 from the left feature tree.",
          "expected_visible_result": "Sketch 1 becomes highlighted.",
          "preferred_activation": "dom_js",
          "fallback_activation": "cdp"
        },
        {
          "sequence": 2,
          "action_type": "click",
          "parameters": { "button": "primary" },
          "ui_region": "top feature toolbar",
          "target_label": "Revolve",
          "target_description": "The Revolve tool in the top feature toolbar.",
          "semantic_action": "Open the Revolve tool.",
          "expected_visible_result": "The Revolve feature dialog opens for Sketch 1.",
          "preferred_activation": "dom_js",
          "fallback_activation": "cdp"
        }
      ],
      "narration": {
        "concise": {
          "text": "Let’s revolve Sketch 1.",
          "fal_elevenlabs_audio_url": "fal://elevenlabs/open-revolve-for-sketch-1/concise",
          "duration_ms": 1400
        },
        "detailed": {
          "text": "Let’s revolve Sketch 1. First I’ll select Sketch 1 from the left feature tree, then I’ll click Revolve in the top toolbar.",
          "fal_elevenlabs_audio_url": "fal://elevenlabs/open-revolve-for-sketch-1/detailed",
          "duration_ms": 5600
        }
      },
      "voice_cues": [
        {
          "cue_id": "intro",
          "phase": "before_step",
          "action_sequence": 1,
          "variant": "both",
          "text_ref": "runtime_select:narration.concise.text|narration.detailed.text",
          "start_policy": "play_before_motion",
          "blocking": true
        },
        {
          "cue_id": "success",
          "phase": "after_step",
          "action_sequence": 2,
          "variant": "concise",
          "text_ref": "The Revolve dialog is open.",
          "start_policy": "play_after_validation",
          "blocking": false
        }
      ],
      "dynamic_corrections": {
        "retry": "I didn’t find Sketch 1 where expected, so I’m checking the screen again.",
        "validation_failed": "The Revolve dialog didn’t open, so I’ll pause here instead of continuing.",
        "user_interrupt": "You moved the mouse, so I’ll stop the demonstration and restore the previous Onshape state."
      },
      "expected_end_state": "Sketch 1 is selected and the Revolve feature dialog is open.",
      "uncertainties": []
    }
  ]
}
```

## Voice timing and cue contract

Section 3 selects the audio asset at runtime using `runtime_preferences.detailed_narration`.

- If `detailed_narration=false`, play the concise asset for the step.
- If `detailed_narration=true`, play the detailed asset for the step.
- `blocking=true` means the demonstration waits for the cue to finish before continuing.
- `blocking=false` means the demonstration may continue while the audio finishes.
- Correction cues interrupt normal narration and should be short.

Recommended default timing:

| Mode | Cue timing | Example |
| --- | --- | --- |
| Concise | Before the first visible action or after validation for tiny steps. | “Let’s revolve Sketch 1.” |
| Detailed | Before the first visible action. | “First I’ll select Sketch 1… then I’ll click Revolve…” |
| Retry | Immediately after failed target localization. | “I’m checking the screen again.” |
| Failure | Immediately after failed validation. | “I’ll pause here instead of continuing.” |
| User interrupt | Immediately after the user moves their own mouse or cancels. | “I’ll stop the demonstration and restore the previous state.” |

## Section 3 execution note

Section 3 should prefer virtual element activation for stable DOM targets:

1. Locate the semantic target using DOM/accessibility data and screenshot confirmation.
2. Trigger the target with a JavaScript click or equivalent DOM activation when it is stable and safe.
3. Show the extension’s virtual cursor overlay for teaching, without moving or taking over the user’s real mouse.
4. Fall back to CDP/browser-level input for canvas, WebGL, drag gestures, inaccessible controls, or failed DOM activation.
5. Validate the visible result after every action regardless of activation method.

Voice narration must remain implementation-neutral. It should say “I’ll select Sketch 1” or “I’ll open Revolve,” not “I’ll run a JavaScript click” or “I’ll use CDP.”

## Acceptance criteria

- Every planned step has concise and detailed narration text.
- Every planned step has stored fal-hosted ElevenLabs audio metadata for both variants.
- Runtime switching through `detailed_narration` requires no regeneration.
- Narration describes semantic, user-visible actions and visible results only.
- Detailed narration previews the exact visible actions in order.
- Concise narration stays short and intent-focused.
- Voice cues define when audio plays and whether execution waits.
- Dynamic correction narration exists for retry, validation failure, and user interruption.
- Activation guidance prefers DOM/JavaScript activation for stable DOM targets and CDP fallback for canvas/WebGL or failed DOM activation.
- Output validates against the JSON contract.

## Constraints

- This system plans and generates voice assets; it does not execute Onshape actions.
- TTS generation depends on fal-hosted ElevenLabs availability and should be cached by `step_id`, variant, voice, text hash, and speaking rate.
- Coordinates from System 1 are references only; Section 3 must localize targets against the live Onshape viewport.
- Do not mention raw coordinates, DOM events, CDP, model confidence, or hidden reasoning in spoken narration.
- Keep correction lines short so they do not distract from the user's interrupted workflow.
