# PRD: Tutorial Orchestration and UX

## Objective

Coordinate the live tutorial experience across the browser extension, virtual agent, voice narration, H OpenAI-compatible browser endpoint, and Onshape state validation.

This system decides what the learner sees and hears at runtime:

- when the virtual agent demonstrates an Onshape step,
- when fal-hosted ElevenLabs narration speaks,
- when the overlay asks the learner to try,
- when the agent stops,
- when the demonstrated Onshape state is restored,
- when monitoring and validation begin.

The core UX rule is simple: a real user click stops the virtual agent; mouse movement does not.

## User story

As an Onshape learner, I want the assistant to show a step inside my current document, explain what it is doing, then get out of the way the moment I click to try it myself, without stopping just because I moved my mouse.

## Scope

This is the runtime orchestration layer for the browser extension side panel and overlay. It consumes prepared tutorial steps from the planning/narration system and validation results from the Onshape state system.

## Non-goals

- Do not analyze tutorial videos.
- Do not generate the full tutorial plan.
- Do not use screenshots as final CAD correctness proof.
- Do not build custom Onshape modelling logic here.
- Do not stop the virtual agent on `mousemove`, `pointermove`, hover, cursor drift, or focus changes.
- Do not expose implementation details such as DOM activation, H calls, API restore operations, or coordinates in spoken narration.

## Core product decisions

1. The virtual agent may demonstrate actions in the live browser using H for visual grounding and browser interaction.
2. The learner sees the demonstration result before trying it themselves.
3. The first real learner click/tap is treated as takeover intent.
4. That takeover click is intercepted and not replayed into Onshape.
5. The system restores the Onshape document to the pre-demo baseline before enabling learner input.
6. Mouse movement alone never interrupts the demo and never triggers rollback.
7. fal-hosted ElevenLabs narration is event-driven and can run in either concise or detailed mode.

## Inputs

```json
{
  "session_id": "session_123",
  "tutorial_id": "maker-coin-revolve",
  "voice_detail_mode": "concise",
  "document": {
    "did": "onshape_document_id",
    "wid": "workspace_id",
    "eid": "part_studio_element_id"
  },
  "current_step": {
    "step_id": "open-revolve-for-sketch-1",
    "goal": "Open the Revolve feature for Sketch 1.",
    "preconditions": ["Sketch 1 exists in the left feature tree."],
    "actions": [],
    "narration": {
      "concise": {
        "text": "Let’s revolve Sketch 1.",
        "fal_elevenlabs_audio_url": "https://..."
      },
      "detailed": {
        "text": "Let’s revolve Sketch 1. First I’ll select Sketch 1 from the left feature tree, then I’ll click Revolve in the top toolbar.",
        "fal_elevenlabs_audio_url": "https://..."
      }
    },
    "expected_end_state": "The Revolve dialog is open for Sketch 1."
  }
}
```

## UX surfaces

### Side panel

Shows the tutorial title, current step, progress, selected narration mode, and primary controls:

- Start step
- Pause
- Replay demo
- Skip step
- Try it myself
- Toggle: concise / detailed narration

### On-page overlay

Shows the virtual cursor, target highlights, temporary disabled-input shield during restore, short status messages, and optional correction hints.

Overlay states should be brief and human-readable:

- “Showing the next step…”
- “Click when you’re ready to try.”
- “Resetting the demo state…”
- “Your turn.”
- “Checking your result…”

## State machine

```text
IDLE
  -> STEP_READY
  -> BASELINE_CAPTURING
  -> BASELINE_CAPTURED
  -> AGENT_DEMONSTRATING
  -> DEMO_VISIBLE_WAITING_FOR_CLICK
  -> USER_CLICK_INTERCEPTED
  -> AGENT_STOPPING
  -> RESTORING_BASELINE
  -> USER_ATTEMPT_READY
  -> USER_ATTEMPT_ACTIVE
  -> VALIDATING
  -> STEP_CORRECT | STEP_NEEDS_CORRECTION | STEP_SKIPPED | ERROR_RECOVERABLE
```

## Interaction rules

| User event | During agent demo | During demo-visible wait | During user attempt |
| --- | --- | --- | --- |
| `mousemove` / `pointermove` | Ignore | Ignore | Observe only |
| Hover changes | Ignore | Ignore | Observe only |
| Real `click` / `pointerdown` | Stop agent and restore baseline | Restore baseline and start user attempt | Normal user input |
| Touch tap | Same as click | Same as click | Normal user input |
| Overlay button click | Runs overlay control only | Runs overlay control only | Runs overlay control only |
| Synthetic agent click | Never counts as takeover | Never counts as takeover | Not used |

Implementation must distinguish real learner activation from agent actions. Programmatic clicks, virtual element activations, and H-driven automation events are tagged with an `automation_action_id` and ignored by the takeover listener.

## Voice behavior

Narration is event-driven and uses the pre-generated fal ElevenLabs audio assets from the planning system.

| Event | Concise voice | Detailed voice |
| --- | --- | --- |
| Step starts | “Let’s revolve Sketch 1.” | “Let’s revolve Sketch 1. First I’ll select Sketch 1 from the left feature tree, then I’ll click Revolve in the top toolbar.” |
| Demo completes | “Now you try.” | “That’s the full step. Click when you’re ready, and I’ll reset it so you can do it yourself.” |
| User clicks | “I’ll reset the demo.” | “You clicked to take over, so I’m stopping the demo and restoring the model first.” |
| Restore completes | “Your turn.” | “The demo state is reset. Now select Sketch 1 and open Revolve yourself.” |
| Validation succeeds | “Nice, that’s correct.” | “Nice, your result matches the expected Revolve step.” |
| Validation fails | “Not quite. Let’s look again.” | “That didn’t match the expected result yet. I’ll show the next correction.” |

Voice must never say “I am calling the API,” “I am using H,” “I am dispatching JavaScript,” or anything similar.

## Runtime flow

1. `STEP_READY`
   - Load the current tutorial step.
   - Show the side panel step card.
   - Confirm the Onshape tab is visible and connected.

2. `BASELINE_CAPTURING`
   - Ask the state system to capture the Onshape baseline before any demo action.
   - Required baseline: current microversion, feature list, and geometry summary.

3. `AGENT_DEMONSTRATING`
   - Play the selected narration variant.
   - Use H to inspect the screen and locate the next UI target.
   - Show the virtual cursor and target highlight.
   - Execute the agent action.
   - Tag all agent-originated actions so they do not trigger takeover.

4. `DEMO_VISIBLE_WAITING_FOR_CLICK`
   - Leave the demonstrated result visible.
   - Show “Click when you’re ready to try.”
   - Ignore mouse movement completely.
   - Wait for a real click/tap or an explicit side-panel control.

5. `USER_CLICK_INTERCEPTED`
   - Prevent the first real click/tap from reaching Onshape.
   - Stop any active agent motion, pending H action, and in-progress voice cue.
   - Fire `user.takeover.clicked`.

6. `RESTORING_BASELINE`
   - Show an input-blocking overlay.
   - Ask the state system to restore the baseline.
   - Keep input blocked until the baseline is confirmed.

7. `USER_ATTEMPT_ACTIVE`
   - Remove the input shield.
   - Start 1 screenshot per second H monitoring.
   - H provides progress hints, but final correctness comes from the Onshape API validator.

8. `VALIDATING`
   - When a relevant committed Onshape change is detected, validate via microversion, feature diff, and geometry.
   - Emit correct, correction, or recoverable-error result.

## Event contract

```json
{
  "event": "user.takeover.clicked",
  "session_id": "session_123",
  "step_id": "open-revolve-for-sketch-1",
  "timestamp_ms": 123456,
  "source": "learner",
  "browser_event": {
    "type": "pointerdown",
    "button": 0,
    "is_trusted": true,
    "target_region": "onshape_canvas"
  },
  "effect": {
    "stop_virtual_agent": true,
    "prevent_original_click": true,
    "restore_baseline": true
  }
}
```

```json
{
  "event": "orchestrator.state.changed",
  "session_id": "session_123",
  "step_id": "open-revolve-for-sketch-1",
  "from": "DEMO_VISIBLE_WAITING_FOR_CLICK",
  "to": "RESTORING_BASELINE",
  "reason": "learner_click_takeover"
}
```

## Example timeline: Revolve Sketch 1

1. Side panel shows: “Step 3: Open Revolve for Sketch 1.”
2. Voice concise mode says: “Let’s revolve Sketch 1.”
3. Virtual cursor highlights `Sketch 1` in the feature tree and selects it.
4. Virtual cursor highlights the Revolve button in the top toolbar and activates it.
5. Revolve dialog opens.
6. Overlay says: “Click when you’re ready to try.”
7. Learner moves their mouse toward the feature tree.
   - Nothing stops.
   - No restore starts.
   - No voice interruption fires.
8. Learner clicks inside Onshape.
   - The click is intercepted.
   - The virtual agent stops.
   - Voice says: “I’ll reset the demo.”
   - Baseline restore begins.
9. Baseline restore is confirmed.
10. Overlay says: “Your turn.”
11. H begins monitoring at 1 screenshot per second.
12. Learner performs the step themselves.
13. Onshape API validation classifies the result.
14. Side panel shows success or a correction prompt.

## Failure handling

- If baseline capture fails, do not demonstrate the step.
- If H cannot find the target, pause and offer replay or skip.
- If the learner clicks while restore is already running, keep input blocked and show “Resetting…”
- If restore cannot be confirmed, do not enable user attempt mode.
- If voice audio is unavailable, fall back to on-screen text and continue.
- If validation is ambiguous, show “I’m not fully sure — check this step” and offer replay.

## Acceptance criteria

1. Moving the mouse during a demo does not stop the virtual agent.
2. Moving the mouse while the demo result is visible does not restore the baseline.
3. The first real click/tap during demo or demo-visible wait stops the virtual agent.
4. The first real click/tap is intercepted and is not applied to Onshape.
5. Agent-originated synthetic clicks never trigger learner takeover.
6. The Onshape baseline is restored before learner input is enabled.
7. fal ElevenLabs narration plays the correct concise or detailed variant for each runtime event.
8. During learner attempt, H receives exactly one screenshot per second.
9. Final correctness comes from Onshape API validation, not screenshots alone.
10. The side panel always shows whether the system is demonstrating, resetting, waiting for the learner, validating, or complete.
