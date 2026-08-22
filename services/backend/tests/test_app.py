import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import onshape_assist.app as app_module
from onshape_assist.app import (
    CaptureObservationCommand,
    DemoEnvelope,
    Relay,
    app,
    relay,
)
from onshape_assist.holo import LocalizedPoint


def tutorial_plan() -> dict:
    return {
        "tutorial_id": "maker-coin-revolve",
        "application": "Onshape",
        "output_language": "en",
        "runtime_preferences": {"detailed_narration": False},
        "voice": {
            "provider": "fal_elevenlabs",
            "voice_id": "friendly-tutor",
            "speaking_rate": 1.0,
        },
        "steps": [
            {
                "step_id": "open-revolve",
                "goal": "Open Revolve for Sketch 1.",
                "preconditions": ["Sketch 1 is visible."],
                "actions": [
                    {
                        "sequence": 1,
                        "action_type": "click",
                        "parameters": {"button": "primary"},
                        "ui_region": "feature tree",
                        "target_label": "Sketch 1",
                        "target_description": "Sketch 1 in the feature tree.",
                        "semantic_action": "Select Sketch 1.",
                        "expected_visible_result": "Sketch 1 is highlighted.",
                        "preferred_activation": "dom_js",
                        "fallback_activation": "cdp",
                    }
                ],
                "narration": {
                    "concise": {
                        "text": "Let's revolve Sketch 1.",
                        "fal_elevenlabs_audio_url": "fal://open-revolve/concise",
                        "duration_ms": 1400,
                    },
                    "detailed": {
                        "text": "First I'll select Sketch 1, then open Revolve.",
                        "fal_elevenlabs_audio_url": "fal://open-revolve/detailed",
                        "duration_ms": 3200,
                    },
                },
                "voice_cues": [
                    {
                        "cue_id": "intro",
                        "phase": "before_step",
                        "action_sequence": 1,
                        "variant": "both",
                        "text_ref": "runtime_select:narration.concise.text|narration.detailed.text",
                        "start_policy": "play_before_motion",
                        "blocking": True,
                    }
                ],
                "dynamic_corrections": {
                    "retry": "I'll check the screen again.",
                    "validation_failed": "That did not open, so I'll pause.",
                    "user_interrupt": "You moved the mouse, so I'll stop.",
                },
                "expected_end_state": "The Revolve dialog is open.",
                "uncertainties": ["Toolbar position may vary."],
            }
        ],
    }


def plan_with_action(action_type: str, parameters: dict | None = None) -> dict:
    plan = tutorial_plan()
    action = plan["steps"][0]["actions"][0]
    action["action_type"] = action_type
    if parameters is None:
        action.pop("parameters", None)
    else:
        action["parameters"] = parameters
    return plan


def test_health_reports_ok():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_command_wraps_in_versioned_envelope():
    client = TestClient(app)

    response = client.post("/commands", json={"type": "move", "x": 20, "y": 40})

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["sequence"] >= 1
    assert body["command"] == {
        "type": "move",
        "x": 20,
        "y": 40,
        "duration_ms": None,
    }


def test_cli_style_navigation_command_is_valid():
    client = TestClient(app)

    response = client.post("/commands", json={"type": "navigate", "direction": "right"})

    assert response.status_code == 200
    assert response.json()["command"]["direction"] == "right"


def test_invalid_move_missing_y_is_rejected():
    client = TestClient(app)

    response = client.post("/commands", json={"type": "move", "x": 20})

    assert response.status_code == 422


def test_full_tutorial_plan_can_be_loaded_and_relayed_at_runtime():
    client = TestClient(app)
    relay.last_envelope = None

    with client.websocket_connect(
        "/ws/extension", headers={"origin": "https://cad.onshape.com"}
    ) as websocket:
        response = client.post(
            "/commands",
            json={"type": "load_tutorial", "plan": tutorial_plan(), "step": 1},
        )
        relayed = websocket.receive_json()

    assert response.status_code == 200
    assert relayed == response.json()
    command = relayed["command"]
    assert command["plan"]["tutorial_id"] == "maker-coin-revolve"
    assert command["plan"]["steps"][0]["actions"][0]["target_label"] == "Sketch 1"
    assert command["plan"]["steps"][0]["narration"]["detailed"]["duration_ms"] == 3200


def test_empty_tutorial_is_rejected():
    client = TestClient(app)

    plan = tutorial_plan()
    plan["steps"] = []
    response = client.post("/commands", json={"type": "load_tutorial", "plan": plan})

    assert response.status_code == 422


def test_load_tutorial_without_plan_is_rejected():
    client = TestClient(app)

    response = client.post("/commands", json={"type": "load_tutorial"})

    assert response.status_code == 422


def test_invalid_nested_tutorial_data_is_rejected():
    client = TestClient(app)
    plan = tutorial_plan()
    plan["steps"][0]["actions"][0]["action_type"] = "teleport"
    response = client.post("/commands", json={"type": "load_tutorial", "plan": plan})

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("action_type", "parameters"),
    [
        ("move", {"duration_ms": 420}),
        ("click", {"button": "primary"}),
        ("double_click", {"button": "primary", "interval_ms": 120}),
        (
            "drag",
            {
                "end_target_label": "Axis",
                "end_target_description": "The vertical construction line.",
                "duration_ms": 700,
            },
        ),
        ("keypress", {"key": "Enter", "modifiers": ["control"], "repeat": 1}),
        ("type", {"text": "25 mm", "clear_existing": True, "submit": True}),
        ("scroll", {"delta_x": 0, "delta_y": 640, "duration_ms": 300}),
        ("wait", {"duration_ms": None, "condition": "The dialog is visible."}),
        (
            "selection",
            {"items": ["Sketch 1", "Axis"], "mode": "replace", "confirm": False},
        ),
    ],
)
def test_action_specific_parameters_are_accepted(action_type: str, parameters: dict):
    client = TestClient(app)

    response = client.post(
        "/commands",
        json={"type": "load_tutorial", "plan": plan_with_action(action_type, parameters)},
    )

    assert response.status_code == 200
    action = response.json()["command"]["plan"]["steps"][0]["actions"][0]
    assert action["action_type"] == action_type
    assert action["parameters"] == parameters


@pytest.mark.parametrize(
    ("action_type", "parameters"),
    [
        ("type", {"button": "primary"}),
        ("scroll", {"delta_x": 0, "delta_y": 0, "duration_ms": 300}),
        ("wait", {"duration_ms": None, "condition": None}),
        ("selection", {"items": [], "mode": "replace", "confirm": False}),
        ("click", {"button": "primary", "text": "unexpected"}),
    ],
)
def test_invalid_action_specific_parameters_are_rejected(
    action_type: str, parameters: dict
):
    client = TestClient(app)

    response = client.post(
        "/commands",
        json={"type": "load_tutorial", "plan": plan_with_action(action_type, parameters)},
    )

    assert response.status_code == 422


def test_action_parameters_are_required():
    client = TestClient(app)

    response = client.post(
        "/commands",
        json={"type": "load_tutorial", "plan": plan_with_action("click")},
    )

    assert response.status_code == 422


def test_websocket_rejects_unknown_web_origin():
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as rejected, client.websocket_connect(
        "/ws/extension", headers={"origin": "https://malicious.example"}
    ):
        pass

    assert rejected.value.code == 1008


@pytest.mark.anyio
async def test_reconnect_does_not_replay_ephemeral_computer_use_commands():
    class FakeWebSocket:
        def __init__(self):
            self.accepted = False
            self.sent: list[dict[str, Any]] = []

        async def accept(self):
            self.accepted = True

        async def send_json(self, value):
            self.sent.append(value)

    local_relay = Relay()
    local_relay.last_envelope = DemoEnvelope(
        sequence=1,
        sent_at="2026-08-22T00:00:00+00:00",
        command=CaptureObservationCommand(
            type="capture_observation", request_id="observation_1"
        ),
    )
    websocket = FakeWebSocket()

    await local_relay.connect(websocket)  # type: ignore[arg-type]

    assert websocket.accepted is True
    assert websocket.sent == []


def test_computer_use_endpoint_round_trips_extension_events(monkeypatch):
    class FakeHolo:
        async def localize(self, screenshot_data_url, context):
            assert screenshot_data_url == "data:image/png;base64,c2NyZWVu"
            assert context.target_label == "Sketch 1"
            return LocalizedPoint(x=500, y=250)

    monkeypatch.setattr(app_module, "holo_factory", FakeHolo)
    relay.last_envelope = None
    responses = []

    with TestClient(app) as client, client.websocket_connect(
        "/ws/extension", headers={"origin": "https://cad.onshape.com"}
    ) as websocket:
        worker = threading.Thread(
            target=lambda: responses.append(
                client.post(
                    "/computer-use/demonstrate",
                    json={
                        "action": tutorial_plan()["steps"][0]["actions"][0],
                        "step_goal": "Open Revolve",
                        "execute": True,
                    },
                )
            )
        )
        worker.start()

        capture = websocket.receive_json()
        assert capture["command"]["type"] == "capture_observation"
        request_id = capture["command"]["request_id"]
        websocket.send_json(
            {
                "version": 1,
                "type": "extension.event",
                "tab_id": 7,
                "event": {
                    "type": "observation.captured",
                    "request_id": request_id,
                    "screenshot_data_url": "data:image/png;base64,c2NyZWVu",
                    "viewport": {
                        "width": 1440,
                        "height": 900,
                        "device_pixel_ratio": 1,
                    },
                    "url": "https://cad.onshape.com/documents/demo/w/one/e/two",
                },
            }
        )

        move = websocket.receive_json()
        assert move["command"] == {
            "type": "move",
            "x": 720,
            "y": 225,
            "duration_ms": 420,
        }
        execute = websocket.receive_json()
        assert execute["command"]["type"] == "execute_action"
        assert execute["command"]["target"] == {"x": 720, "y": 225}
        action_id = execute["command"]["action_id"]
        websocket.send_json(
            {
                "version": 1,
                "type": "extension.event",
                "tab_id": 7,
                "event": {
                    "type": "action.completed",
                    "action_id": action_id,
                    "success": True,
                    "reason": None,
                    "element_description": "Sketch 1",
                },
            }
        )
        worker.join(timeout=3)

    assert not worker.is_alive()
    assert responses[0].status_code == 200
    assert responses[0].json()["success"] is True
    assert responses[0].json()["viewport_target"] == {"x": 720, "y": 225}
