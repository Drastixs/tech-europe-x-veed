# Dependencies

## Supported runtime

- Chromium MV3 extension — the on-page overlay, virtual cursor, takeover listener, and browser relay client.
- Local FastAPI backend — relay, video analysis, planning, and Onshape state services.
- Onshape REST API — baseline capture, restore confirmation, and committed-state validation.

The product does not use a desktop overlay, global input hooks, PySide6, or pynput.

## Shared contracts

[`contracts/runtime-v1.schema.json`](contracts/runtime-v1.schema.json) defines the
versioned tutorial-plan, runtime-event, state-snapshot, validation-outcome, and
error payloads. The canonical Revolve fixture is validated by both backend and
extension tests.
