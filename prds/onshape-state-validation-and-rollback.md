# PRD: Onshape State Validation and Rollback

## Objective

Validate whether the learner has correctly repeated a demonstrated Onshape tutorial step, while protecting them from the agent's temporary demonstration changes.

This system receives the executable tutorial plan and coordinates with Section 3's computer-use system to demonstrate the step in the live browser with the H Holo OpenAI-compatible endpoint. It leaves the demonstrated result visible and only restores the original baseline when the learner intentionally starts interacting with the simulation themselves. During the learner's attempt, H monitors screenshots at exactly one screenshot per second, while the Onshape API is the authoritative source for final correctness.

## User story

As an Onshape learner, I want the agent to show me the next CAD action inside my current document, then reset the model when I start trying it myself, so I can practice without manually undoing the demo or losing my own progress.

## Core decision

Use two different validation layers:

- H Holo observes and drives the browser UI from screenshots. It handles visual grounding, progress detection, and soft coaching.
- Onshape API validates committed CAD state. It is the source of truth for whether the model changed correctly.

Do not use screenshot interpretation as the final CAD validator. Screenshots are for guidance; Onshape microversions, feature diffs, and resulting geometry decide the outcome.

## Inputs

```json
{
  "tutorial_id": "maker-coin-revolve",
  "document": {
    "did": "onshape_document_id",
    "wid": "workspace_id",
    "eid": "part_studio_element_id"
  },
  "step": {
    "step_id": "open-revolve-for-sketch-1",
    "goal": "Create Revolve 1 from Sketch 1.",
    "expected_start_state": "Sketch 1 exists and no Revolve 1 feature exists.",
    "expected_user_actions": [
      "Select Sketch 1 from the feature tree.",
      "Open Revolve.",
      "Select the vertical construction line as the revolve axis.",
      "Confirm the Revolve dialog."
    ],
    "expected_committed_result": {
      "new_feature_type": "revolve",
      "new_feature_name": "Revolve 1",
      "source_sketch": "Sketch 1",
      "operation": "new",
      "angle_degrees": 360
    }
  },
  "runtime": {
    "screenshot_rate_hz": 1,
    "h_context_screenshot_window": 3,
    "voice_detail_mode": "concise|detailed"
  }
}
```

## Functional requirements

1. Capture a baseline before the agent demonstration:
   - current document/workspace microversion,
   - Part Studio feature list,
   - resulting geometry summary for the target element.
2. Demonstrate the tutorial step through H Holo using screenshot observations and localized targets. H may return normalized coordinates or structured actions, but runtime code executes the actions.
3. Keep the demonstrated result visible after the demo finishes.
4. Detect only intentional learner takeover events: `pointerdown`, touch start, or relevant Onshape `keydown`. Passive mouse movement never counts.
5. Intercept the first intentional learner event, pause it, stop agent execution, and restore the Onshape workspace to the captured baseline.
6. Confirm the baseline restore before reenabling user input.
7. After reenabling input, let the learner perform the action themselves. Do not replay the intercepted click automatically.
8. Monitor the learner attempt with H at exactly one screenshot per second.
9. Keep only the last 3 screenshots in H context; older screenshots become text summaries.
10. Validate final committed CAD state through the Onshape API using only:
    - current microversion,
    - feature-list diff,
    - resulting geometry.
11. Emit structured events for the UI overlay, narration system, and analytics store.

## Non-goals

- Do not rely on the Onshape browser DOM as the source of truth for final model correctness.
- Do not monitor every browser event. The reliable takeover triggers are `pointerdown`, touch start, and relevant Onshape `keydown`.
- Do not use hidden or undocumented Onshape client internals.
- Do not restore automatically just because the learner moves the mouse; hover, cursor drift, and accidental movement must be ignored.
- Do not overwrite user work if the workspace no longer matches the expected demonstration state.

## State machine

```text
IDLE
  -> BASELINE_CAPTURED
  -> AGENT_DEMONSTRATING
  -> DEMO_VISIBLE_WAITING_FOR_USER
  -> USER_TAKEOVER_INTERCEPTED
  -> RESTORING_BASELINE
  -> BASELINE_CONFIRMED
  -> USER_ATTEMPT_ACTIVE
  -> VALIDATING_COMMITTED_STATE
  -> OUTCOME_CORRECT | OUTCOME_INCORRECT | OUTCOME_NO_COMMITTED_CHANGE | OUTCOME_ALREADY_AHEAD | NEEDS_HUMAN_REVIEW
```

## Events

| Event | Fired when | Consumer |
| --- | --- | --- |
| `baseline.captured` | Microversion, feature list, and geometry snapshot are stored. | Runtime, validator |
| `agent.demo.started` | H begins driving/localizing the browser UI for the tutorial step. | Overlay, narration |
| `agent.demo.completed` | The demonstrated result is visible in Onshape. | Overlay |
| `user.takeover.detected` | First `pointerdown`, touch start, or relevant Onshape `keydown` occurs. | Runtime |
| `baseline.restore.started` | The intercepted event is paused and Onshape restore begins. | Overlay, narration |
| `baseline.restore.confirmed` | API confirms the workspace matches the baseline. | Runtime |
| `user.attempt.started` | User input is reenabled. | H monitor, narration |
| `h.observation.received` | H returns the 1 Hz progress observation. | Overlay, coaching |
| `onshape.change.detected` | Current microversion differs after a user commit. | Validator |
| `validation.completed` | API checks classify the outcome. | Overlay, analytics, narration |

## Runtime flow

1. Baseline capture
   - Call Onshape to read the current microversion for the workspace.
   - Fetch the Part Studio feature list.
   - Fetch or compute a compact geometry summary for the relevant part/body state, such as part count, volume/bounding box where available, and named feature outputs.

2. Agent demonstration
   - Send H a screenshot plus the next action target.
   - For toolbar/buttons/tree entries, prefer H element localization and JS/virtual element activation when the target can be safely resolved.
   - For canvas operations or inaccessible UI, use H's agent loop to return the next UI action and have the runtime execute it.
   - The voice layer says what the user sees, not the mechanism: “Let’s revolve Sketch 1,” or in detailed mode, “First I’ll select Sketch 1 from the left feature tree, then I’ll open Revolve from the top toolbar.”

3. Demo-visible pause
   - Leave the demonstrated Onshape state visible.
   - Arm the takeover listener.
   - Ignore passive mouse movement, hover state changes, and cursor drift.

4. User takeover and baseline restore
   - On first `pointerdown`, touch start, or relevant Onshape `keydown`, prevent the event from reaching Onshape.
   - Relevant keyboard input means a key event that would affect Onshape state or the active Onshape tool, such as typing into a dimension field, confirming a dialog, deleting a selection, or using a modelling shortcut. Browser shortcuts, overlay controls, and focus outside the Onshape work area do not trigger takeover.
   - Stop agent execution and H monitoring for the demo.
   - Restore the document/workspace back to the baseline microversion using the supported Onshape restore/history capability.
   - Re-fetch the three baseline measurements.
   - Reenable input only when the restored state matches.

5. User attempt monitoring
   - Capture one browser screenshot per second.
   - Send each screenshot to H with the expected step, latest action status, and last 3 screenshot context.
   - H returns progress observations and coaching suggestions, but cannot mark the CAD result correct by itself.

6. API validation
   - When a committed Onshape change is detected, compare current state to baseline and expected result.
   - Classify the outcome and fire narration/overlay events.

## H observation contract

```json
{
  "step_id": "open-revolve-for-sketch-1",
  "timestamp_ms": 123456,
  "screenshot_sequence": 7,
  "expected_step": "Create Revolve 1 from Sketch 1.",
  "observed_action": {
    "phase": "selecting_source|opening_tool|editing_dialog|confirming|waiting|off_track|unknown",
    "description": "User has selected Sketch 1 in the left feature tree.",
    "ui_target": "Sketch 1",
    "cursor_position": { "x": 84, "y": 298 },
    "confidence": 0.87
  },
  "progress": {
    "completed_expected_actions": ["select_sketch_1"],
    "next_expected_action": "open_revolve_tool",
    "blocked_reason": null
  },
  "intervention": {
    "type": "none|hint|warning|pause",
    "voice_text": null
  }
}
```

## Validation output contract

```json
{
  "step_id": "open-revolve-for-sketch-1",
  "baseline": {
    "microversion_id": "mv_before_demo",
    "feature_fingerprint": "hash_of_feature_list",
    "geometry_fingerprint": "hash_of_geometry_summary"
  },
  "current": {
    "microversion_id": "mv_after_user_attempt",
    "feature_diff": [
      {
        "change_type": "added",
        "feature_type": "revolve",
        "feature_name": "Revolve 1",
        "parameters_summary": {
          "source": "Sketch 1",
          "angle_degrees": 360,
          "axis": "vertical construction line"
        }
      }
    ],
    "geometry_summary": {
      "part_count": 1,
      "created_solid": true,
      "shape_matches_expected": true
    }
  },
  "outcome": "correct",
  "confidence": 0.91,
  "fires": [
    "onshape.change.detected",
    "validation.completed",
    "voice.play.success"
  ],
  "user_message": "Nice — your Revolve 1 was created from Sketch 1."
}
```

## Worked example: Revolve Sketch 1

### Setup

The tutorial step is: create `Revolve 1` from `Sketch 1` using the vertical construction line as the revolve axis.

Baseline:

```json
{
  "microversion_id": "mv_100",
  "features": ["Origin", "Front", "Top", "Right", "Sketch 1"],
  "geometry": {
    "solid_count": 0,
    "surface_count": 0
  }
}
```

### What fires

1. Agent demonstrates the step.
   - H localizes `Sketch 1` in the feature tree.
   - Runtime selects it.
   - H localizes the Revolve toolbar button.
   - Runtime opens Revolve, selects the axis, and confirms.
   - `agent.demo.completed` fires.
   - Voice concise: “Let’s revolve Sketch 1.”
   - Voice detailed: “Let’s revolve Sketch 1. First I’ll select Sketch 1 from the left feature tree, then I’ll open Revolve from the top toolbar, choose the vertical construction line as the axis, and confirm the feature.”

2. Learner clicks the canvas to try it themselves.
   - Browser sees `pointerdown`.
   - `user.takeover.detected` fires.
   - The event is prevented.
   - `baseline.restore.started` fires.
   - Onshape restore is called for baseline `mv_100`.
   - API rechecks microversion, feature list, and geometry.
   - `baseline.restore.confirmed` fires.
   - Input is reenabled.
   - Voice: “I’ve reset the demo state. Now you try the revolve.”

3. Learner selects `Sketch 1`.
   - H receives the next 1 Hz screenshot.
   - H returns `phase="selecting_source"` and `completed_expected_actions=["select_sketch_1"]`.
   - `h.observation.received` fires.
   - No Onshape validation fires yet if nothing has been committed.

4. Learner opens Revolve.
   - H sees the Revolve dialog open.
   - H returns `phase="editing_dialog"` and `next_expected_action="select_revolve_axis"`.
   - Optional voice hint if paused: “Now choose the vertical construction line as the revolve axis.”

5. Learner confirms the Revolve dialog.
   - Onshape creates a new microversion.
   - `onshape.change.detected` fires.
   - Validator fetches feature list and geometry.
   - Feature diff shows one new revolve feature.
   - Geometry shows the expected solid result.
   - `validation.completed` fires with `outcome="correct"`.
   - Voice: “That’s correct — the revolve was created from Sketch 1.”

## Outcome rules

| Outcome | Rule | User-facing response |
| --- | --- | --- |
| `correct` | Microversion changed, feature diff matches expected feature, and geometry matches expected result. | Success narration and next step unlock. |
| `incorrect` | Microversion changed, but feature diff or geometry does not match expected result. | Targeted correction from H observation plus API mismatch summary. |
| `no_committed_change` | User interacted, but current microversion remains equivalent to baseline. | Prompt them to finish/confirm the Onshape dialog. |
| `already_ahead` | Current workspace already contains the expected result before the attempt starts. | Offer to continue or reset to the tutorial baseline. |
| `needs_human_review` | API result is ambiguous, restore confirmation fails, or concurrent edits are detected. | Pause and ask the user what to do. |

## Safety and race conditions

- Store API credentials server-side only.
- Run tutorials in a copied or dedicated Onshape document/workspace whenever possible.
- Before restoring, confirm the current workspace is still the agent's demonstrated state or a direct descendant of it.
- If another user or tab changes the document between demo completion and learner takeover, pause instead of restoring.
- If restore succeeds visually but the API measurements do not match, keep input disabled and show a recovery prompt.
- Treat Onshape entity IDs carefully because geometry IDs can change across microversions; use Onshape's ID translation/associativity APIs only when identity tracking is required across model changes.
- Never fire success from H screenshots alone.

## Nonfunctional requirements

- Baseline capture should complete in under 3 seconds for normal hackathon tutorial documents.
- Restore confirmation should complete in under 5 seconds for normal Part Studios.
- H monitoring must run at exactly 1 screenshot per second during user attempts.
- The validator should tolerate minor floating-point differences in geometry summaries.
- All state transitions must be logged with `tutorial_id`, `step_id`, timestamp, baseline microversion, current microversion, and outcome.

## Acceptance criteria

1. A demonstrated Onshape change remains visible until the learner intentionally clicks, touches the UI, or sends relevant keyboard input to Onshape.
2. The first intentional learner event is intercepted and does not accidentally edit the demonstrated state.
3. Passive mouse movement, hover changes, browser shortcuts, and overlay interactions do not stop the virtual agent or trigger restoration.
4. The baseline restore is confirmed by microversion, feature list, and geometry before the user can continue.
5. During the learner attempt, H receives one screenshot per second and never more than the last 3 screenshots in context.
6. A correct Revolve-from-Sketch-1 attempt returns `outcome="correct"` only after Onshape API validation.
7. A wrong tool, wrong axis, cancelled dialog, or no committed change produces a distinct non-success outcome.
8. If concurrent edits are detected, the system pauses rather than restoring or validating against stale assumptions.

## References

- H Company, [About the Models API](https://hub.hcompany.ai/about-the-models-api): Holo models are exposed through an OpenAI-compatible multimodal API for real UI operation.
- H Company, [Agent loop](https://hub.hcompany.ai/agent-loop): structured Holo agent loop, normalized `[0, 1000]` coordinates, and the recommendation to keep at most the last 3 screenshots in context.
- H Company, [Element localization](https://hub.hcompany.ai/element-localization): single-turn screenshot-to-coordinate localization for UI targets.
- Onshape, [Introduction to the Onshape REST API](https://onshape-public.github.io/docs/api-intro/): document/workspace/version/microversion model and REST conventions.
- Onshape, [Features API](https://onshape-public.github.io/docs/api-adv/featureaccess/): Part Studio feature-list access and feature representation.
- Onshape, [Restore a design after unwanted changes](https://www.onshape.com/en/resource-center/tech-tips/restore-cad-model-design-version-after-unwanted-changes): restore from a selected microversion and tab-level restore behavior.
- Onshape, [Associativity](https://onshape-public.github.io/docs/api-adv/associativity/): entity IDs can change across microversions, with APIs available for ID translation when needed.
