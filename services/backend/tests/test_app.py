import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from onshape_assist.app import app


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
        "steps": None,
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


def test_tutorial_steps_can_be_loaded_at_runtime():
    client = TestClient(app)

    response = client.post(
        "/commands",
        json={
            "type": "load_tutorial",
            "steps": [
                {"step_id": "select-sketch", "text": "Select Sketch 1."},
                {"step_id": "open-revolve", "text": "Open Revolve."},
            ],
            "step": 2,
        },
    )

    assert response.status_code == 200
    assert response.json()["command"]["steps"][1]["step_id"] == "open-revolve"


def test_empty_tutorial_is_rejected():
    client = TestClient(app)

    response = client.post("/commands", json={"type": "load_tutorial", "steps": []})

    assert response.status_code == 422


def test_websocket_rejects_unknown_web_origin():
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as rejected, client.websocket_connect(
        "/ws/extension", headers={"origin": "https://malicious.example"}
    ):
        pass

    assert rejected.value.code == 1008
