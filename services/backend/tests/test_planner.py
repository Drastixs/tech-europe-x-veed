from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import onshape_assist.app as app_module
from onshape_assist.app import TutorialPlan, app, relay
from onshape_assist.planner import OpenAIPlanner, PlannerError


def planned_tutorial() -> dict:
    return {
        "tutorial_id": "model-supplied-id",
        "application": "Onshape",
        "output_language": "en",
        "runtime_preferences": {"detailed_narration": False},
        "voice": {
            "provider": "fal_elevenlabs",
            "voice_id": "model-supplied-voice",
            "speaking_rate": 1.0,
        },
        "steps": [
            {
                "step_id": "open-revolve",
                "goal": "Open Revolve.",
                "preconditions": ["Sketch 1 is visible."],
                "actions": [
                    {
                        "sequence": 1,
                        "action_type": "click",
                        "ui_region": "toolbar",
                        "target_label": "Revolve",
                        "target_description": "Revolve in the top toolbar.",
                        "semantic_action": "Open Revolve.",
                        "expected_visible_result": "The Revolve dialog opens.",
                        "preferred_activation": "dom_js",
                        "fallback_activation": "cdp",
                    }
                ],
                "narration": {
                    "concise": {
                        "text": "Let's open Revolve.",
                        "fal_elevenlabs_audio_url": "pending://tts/open-revolve/concise",
                        "duration_ms": 0,
                    },
                    "detailed": {
                        "text": "I'll click Revolve in the top toolbar.",
                        "fal_elevenlabs_audio_url": "pending://tts/open-revolve/detailed",
                        "duration_ms": 0,
                    },
                },
                "voice_cues": [
                    {
                        "cue_id": "step-intro",
                        "phase": "before_step",
                        "action_sequence": 1,
                        "variant": "both",
                        "text_ref": (
                            "runtime_select:narration.concise.text|narration.detailed.text"
                        ),
                        "start_policy": "play_before_motion",
                        "blocking": True,
                    }
                ],
                "dynamic_corrections": {
                    "retry": "I'll try that again.",
                    "validation_failed": "That did not open, so I'll pause.",
                    "user_interrupt": "You've taken control, so I'll stop.",
                },
                "expected_end_state": "The Revolve dialog is open.",
                "uncertainties": [],
            }
        ],
    }


def planning_request() -> dict:
    return {
        "video_analysis": {
            "transcript": "Click Revolve.",
            "actions": [{"timestamp_ms": 1200, "action": "click", "target": "Revolve"}],
        },
        "tutorial_id": "requested-id",
        "output_language": "en-GB",
        "runtime_preferences": {"detailed_narration": True},
        "voice": {
            "provider": "fal_elevenlabs",
            "voice_id": "requested-voice",
            "speaking_rate": 0.95,
        },
    }


def test_openai_planner_uses_responses_strict_schema_and_server_key():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"status": "completed", "output_text": json.dumps(planned_tutorial())},
        )

    async def run() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            planner = OpenAIPlanner(
                api_key="server-secret",
                model="test-model",
                base_url="https://openai.test/v1",
                client=client,
            )
            return await planner.generate(
                input_payload={"video_analysis": {}},
                schema=TutorialPlan.model_json_schema(),
            )

    result = asyncio.run(run())

    assert result["steps"][0]["step_id"] == "open-revolve"
    assert captured["authorization"] == "Bearer server-secret"
    assert captured["body"]["model"] == "test-model"
    output_format = captured["body"]["text"]["format"]
    assert output_format["type"] == "json_schema"
    assert output_format["strict"] is True
    assert output_format["schema"]["additionalProperties"] is False
    assert "server-secret" not in captured["body"]["input"]


def test_openai_planner_accepts_nested_output_text():
    response = {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(planned_tutorial())}],
            }
        ],
    }

    async def run() -> dict:
        transport = httpx.MockTransport(lambda _: httpx.Response(200, json=response))
        async with httpx.AsyncClient(transport=transport) as client:
            return await OpenAIPlanner(api_key="key", client=client).generate(
                input_payload={}, schema={"type": "object"}
            )

    assert asyncio.run(run())["tutorial_id"] == "model-supplied-id"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}},
            "did not complete: max_output_tokens",
        ),
        (
            {
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}],
            },
            "refused",
        ),
    ],
)
def test_openai_planner_rejects_incomplete_and_refusal_responses(body: dict, expected: str):
    async def run() -> None:
        transport = httpx.MockTransport(lambda _: httpx.Response(200, json=body))
        async with httpx.AsyncClient(transport=transport) as client:
            await OpenAIPlanner(api_key="key", client=client).generate(
                input_payload={}, schema={"type": "object"}
            )

    with pytest.raises(PlannerError, match=expected):
        asyncio.run(run())


def test_plan_endpoint_generates_enriches_and_relays(monkeypatch):
    generated = planned_tutorial()
    enriched_calls: list[TutorialPlan] = []

    class FakePlanner:
        async def generate(self, *, input_payload: dict, schema: dict) -> dict:
            assert input_payload["video_analysis"]["transcript"] == "Click Revolve."
            assert input_payload["tutorial_metadata"]["voice"]["voice_id"] == "requested-voice"
            assert schema["additionalProperties"] is False
            return generated

    async def enrich(plan: TutorialPlan) -> TutorialPlan:
        enriched_calls.append(plan)
        plan.steps[0].narration.concise.fal_elevenlabs_audio_url = "https://audio.test/concise.mp3"
        plan.steps[0].narration.concise.duration_ms = 1500
        return plan

    monkeypatch.setattr(app_module, "planner_factory", FakePlanner)
    monkeypatch.setattr(app_module, "narration_enricher", enrich)
    relay.last_envelope = None

    with (
        TestClient(app) as client,
        client.websocket_connect(
            "/ws/extension", headers={"origin": "https://cad.onshape.com"}
        ) as websocket,
    ):
        response = client.post("/tutorials/plan", json=planning_request())
        relayed = websocket.receive_json()

    assert response.status_code == 200
    assert relayed == response.json()
    plan = response.json()["command"]["plan"]
    assert plan["tutorial_id"] == "requested-id"
    assert plan["output_language"] == "en-GB"
    assert plan["runtime_preferences"]["detailed_narration"] is True
    assert plan["voice"]["voice_id"] == "requested-voice"
    assert plan["steps"][0]["narration"]["concise"]["duration_ms"] == 1500
    assert len(enriched_calls) == 1


def test_plan_endpoint_maps_missing_api_key_to_service_unavailable(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "planner_factory",
        lambda: OpenAIPlanner(api_key=""),
    )

    with TestClient(app) as client:
        response = client.post("/tutorials/plan", json=planning_request())

    assert response.status_code == 503
    assert response.json()["detail"] == "OPENAI_API_KEY is not configured"


def test_generated_plan_with_extra_nested_fields_fails_contract(monkeypatch):
    generated = planned_tutorial()
    generated["steps"][0]["unexpected"] = True

    class FakePlanner:
        async def generate(self, **_: object) -> dict:
            return generated

    monkeypatch.setattr(app_module, "planner_factory", FakePlanner)

    with TestClient(app) as client:
        response = client.post("/tutorials/plan", json=planning_request())

    assert response.status_code == 502
    assert "failed contract validation" in response.json()["detail"]
