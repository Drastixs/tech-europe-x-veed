import type { TutorialPlan } from "./protocol";

export const tutorialPlanFixture: TutorialPlan = {
  tutorial_id: "maker-coin-revolve",
  application: "Onshape",
  output_language: "en",
  runtime_preferences: { detailed_narration: false },
  voice: {
    provider: "fal_elevenlabs",
    voice_id: "friendly-tutor",
    speaking_rate: 1
  },
  steps: [
    {
      step_id: "select-sketch",
      goal: "Select Sketch 1.",
      preconditions: ["Sketch 1 is visible."],
      actions: [
        {
          sequence: 1,
          action_type: "click",
          parameters: { button: "primary" },
          ui_region: "feature tree",
          target_label: "Sketch 1",
          target_description: "Sketch 1 in the feature tree.",
          icon_description: "A blue sketch glyph beside the Sketch 1 label.",
          semantic_action: "Select Sketch 1.",
          expected_visible_result: "Sketch 1 is highlighted.",
          preferred_activation: "dom_js",
          fallback_activation: "cdp"
        }
      ],
      narration: {
        concise: {
          text: "Select Sketch 1.",
          fal_elevenlabs_audio_url: "fal://select-sketch/concise",
          duration_ms: 1000
        },
        detailed: {
          text: "I'll select Sketch 1 from the feature tree.",
          fal_elevenlabs_audio_url: "fal://select-sketch/detailed",
          duration_ms: 2400
        }
      },
      voice_cues: [
        {
          cue_id: "intro",
          phase: "before_step",
          action_sequence: 1,
          variant: "both",
          text_ref: "runtime_select:narration.concise.text|narration.detailed.text",
          start_policy: "play_before_motion",
          blocking: true
        }
      ],
      dynamic_corrections: {
        retry: "I'll check the screen again.",
        target_relocated: "The target moved, so I'll locate it again.",
        validation_failed: "That did not open, so I'll pause.",
        user_interrupt: "You moved the mouse, so I'll stop."
      },
      expected_end_state: "Sketch 1 is highlighted.",
      uncertainties: []
    },
    {
      step_id: "open-revolve",
      goal: "Open Revolve.",
      preconditions: ["Sketch 1 is selected."],
      actions: [
        {
          sequence: 1,
          action_type: "click",
          parameters: { button: "primary" },
          ui_region: "top toolbar",
          target_label: "Revolve",
          target_description: "The Revolve toolbar button.",
          icon_description: "A profile rotating around a vertical axis.",
          semantic_action: "Open Revolve.",
          expected_visible_result: "The Revolve dialog opens.",
          preferred_activation: "dom_js",
          fallback_activation: "cdp"
        }
      ],
      narration: {
        concise: {
          text: "Open Revolve.",
          fal_elevenlabs_audio_url: "fal://open-revolve/concise",
          duration_ms: 900
        },
        detailed: {
          text: "Next I'll open Revolve from the toolbar.",
          fal_elevenlabs_audio_url: "fal://open-revolve/detailed",
          duration_ms: 2100
        }
      },
      voice_cues: [],
      dynamic_corrections: {
        retry: "I'll locate Revolve again.",
        target_relocated: "Revolve moved, so I'll locate it again.",
        validation_failed: "Revolve did not open, so I'll pause.",
        user_interrupt: "You moved the mouse, so I'll stop."
      },
      expected_end_state: "The Revolve dialog is open.",
      uncertainties: ["Toolbar position can vary."]
    }
  ]
};
