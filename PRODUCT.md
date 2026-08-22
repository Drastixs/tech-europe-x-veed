# Product
## Register
product

## Users

People learning CAD in Onshape who need step-by-step visual guidance without repeatedly switching between a tutorial and their active workspace.

## Product Purpose

Keep learners in context by placing clear, reversible tutorial guidance directly over Onshape. Success means the next action is obvious, the underlying CAD interface remains readable, and the learner stays in control.

## Brand Personality

Precise, calm, quietly futuristic. The interface should feel technically capable without resembling a cinematic sci-fi HUD.

## Anti-references

Opaque panels that hide the workspace, neon-heavy cyberpunk dashboards, decorative glass on every surface, generated concept imagery presented as a real product, and dense control chrome.

## Design Principles

1. Preserve the workspace as the primary surface.
2. Make guidance legible at a glance, then get out of the way.
3. Use translucency and spectral color as state cues, not decoration.
4. Keep every automated action reversible and visibly attributable.
5. Prefer proven interaction patterns from real tools.

## Accessibility & Inclusion

Target WCAG 2.2 AA contrast, visible keyboard focus, reduced-motion support, and redundant state cues that do not rely on color alone.


## technical sections

### Supported Runtime & Contracts

The product runs as a Chromium MV3 extension backed by local FastAPI services.
The extension presents guidance without moving the learner's real pointer;
backend services own credentials and validate committed Onshape state. Shared
tutorial plans, runtime events, state snapshots, validation outcomes, and
errors use the versioned contract in
[`contracts/runtime-v1.schema.json`](contracts/runtime-v1.schema.json).

### Video Analysis & Tutorial Extraction
Understand what a video is doing, breakdown based on the video and transcript, using fal video api, to breakdown the current instructions and ui from the video for what the user is really doing, provide a actioonable and time stamped naration for what is going on within the video.

Technical specification and test videos: [Video Analysis and Narration PRD](prds/video-analytis-and-narration.md).

### Tutorial Planning & Voice Narration
Converting the autistic, highly descriptive output into actionalbe steps, actions and lines for the frontend application to relay directly to the user. 

Technical specification: [Tutorial Planning and Voice Narration PRD](prds/tutorial-planning-and-voice-narration.md).

### Computer Use & Virtual Demonstration
Using the direct steps and actions and relaying to the frontend using h computer use pipeline along with dom manipulation to directly interact with the application. JS clicking scripts prefered to cdp. 

### Browser State Monitoring & Validation
Being able to validate an actions has been performed correctly and recording the state using microversion id from onshape in order to rewind the current implementation for what has been accomplished. 

Technical specification: [Onshape State Validation and Rollback PRD](prds/onshape-state-validation-and-rollback.md).

### Tutorial Orchestration & User Experience
Building the UI to be as un intrusive as possible yet prefering to the user settings, for example, the hint toggle uses the voice to take the user through each action in more detail if on, if off it just describes the steps. 

Technical specification: [Tutorial Orchestration and UX PRD](prds/tutorial-orchestration-and-ux.md).
