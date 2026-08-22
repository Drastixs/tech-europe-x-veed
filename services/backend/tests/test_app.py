import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from onshape_assist.app import app, relay


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
        "direction": None,
        "plan": None,
        "step": None,
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


def test_websocket_rejects_unknown_web_origin():
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as rejected, client.websocket_connect(
        "/ws/extension", headers={"origin": "https://malicious.example"}
    ):
        pass

    assert rejected.value.code == 1008
