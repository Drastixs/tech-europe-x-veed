import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from onshape_assist.app import app, relay
from onshape_assist.contracts import RuntimeContractBundle, RuntimeSession

FIXTURE = (
    Path(__file__).resolve().parents[3] / "contracts/fixtures/revolve-from-sketch-1.runtime-v1.json"
)


def test_runtime_contract_fixture_is_accepted():
    bundle = RuntimeContractBundle.model_validate_json(FIXTURE.read_text())

    assert bundle.contract_version == 1
    assert bundle.tutorial_plan.steps[0].actions[0].preferred_activation == "dom_js"
    assert bundle.validation_outcome.outcome == "correct"


def test_runtime_fixture_plan_round_trips_through_the_live_relay():
    bundle = RuntimeContractBundle.model_validate_json(FIXTURE.read_text())
    relay.last_envelope = None
    client = TestClient(app)

    runtime_session = RuntimeSession.model_validate({
        "contract_version": bundle.contract_version,
        "session_id": bundle.state_snapshot.session_id,
        "state_snapshot": bundle.state_snapshot.model_dump(),
        "runtime_events": [event.model_dump() for event in bundle.runtime_events],
        "validation_outcome": bundle.validation_outcome.model_dump(),
        "error": bundle.error.model_dump(),
    })
    response = client.post(
        "/commands",
        json={
            "type": "load_tutorial",
            "plan": bundle.tutorial_plan.model_dump(),
            "step": 1,
            "runtime_session": runtime_session.model_dump(),
        },
    )

    assert response.status_code == 200
    assert response.json()["command"]["plan"] == bundle.tutorial_plan.model_dump()
    assert response.json()["command"]["runtime_session"] == runtime_session.model_dump()


def test_runtime_contract_rejects_unknown_outcomes():
    payload = json.loads(FIXTURE.read_text())
    payload["validation_outcome"]["outcome"] = "maybe_correct"

    with pytest.raises(ValidationError):
        RuntimeContractBundle.model_validate(payload)


def test_runtime_contract_rejects_event_for_another_session():
    payload = json.loads(FIXTURE.read_text())
    payload["runtime_events"][0]["session_id"] = "other-session"

    with pytest.raises(ValidationError):
        RuntimeContractBundle.model_validate(payload)


def test_relay_rejects_runtime_event_for_an_unknown_tutorial_step():
    bundle = RuntimeContractBundle.model_validate_json(FIXTURE.read_text())
    runtime_session = RuntimeSession.model_validate({
        "contract_version": bundle.contract_version,
        "session_id": bundle.state_snapshot.session_id,
        "state_snapshot": bundle.state_snapshot.model_dump(),
        "runtime_events": [
            {**event.model_dump(), "step_id": "unknown-step"} for event in bundle.runtime_events
        ],
    })

    response = TestClient(app).post(
        "/commands",
        json={
            "type": "load_tutorial",
            "plan": bundle.tutorial_plan.model_dump(),
            "runtime_session": runtime_session.model_dump(),
        },
    )

    assert response.status_code == 422
