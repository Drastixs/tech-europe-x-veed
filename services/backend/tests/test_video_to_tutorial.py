from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from test_planner import planned_tutorial

import onshape_assist.app as app_module
from onshape_assist.analysis.models import AnalysisResult
from onshape_assist.app import TutorialPlan, app, relay

REAL_ANALYSIS = Path(__file__).parents[1] / "examples" / "sample-output.json"


def test_video_analysis_flows_into_planning_voice_and_relay(monkeypatch):
    analysis = AnalysisResult.model_validate(json.loads(REAL_ANALYSIS.read_text()))
    captured: dict[str, object] = {}

    async def analyze(request, **kwargs):
        captured["analysis_request"] = request
        captured["analysis_options"] = kwargs
        return analysis

    class FakePlanner:
        async def generate(self, *, input_payload: dict, schema: dict) -> dict:
            captured["planning_input"] = input_payload
            assert schema["additionalProperties"] is False
            return planned_tutorial()

    async def host_narration(plan: TutorialPlan) -> TutorialPlan:
        for tutorial_step in plan.steps:
            for variant_name in ("concise", "detailed"):
                variant = getattr(tutorial_step.narration, variant_name)
                variant.fal_elevenlabs_audio_url = (
                    f"https://audio.test/{tutorial_step.step_id}/{variant_name}.mp3"
                )
                variant.duration_ms = 1000
        return plan

    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    monkeypatch.setattr(app_module, "analyze_video_async", analyze)
    monkeypatch.setattr(app_module, "planner_factory", FakePlanner)
    monkeypatch.setattr(app_module, "narration_enricher", host_narration)
    relay.last_envelope = None

    with (
        TestClient(app) as client,
        client.websocket_connect(
            "/ws/extension", headers={"origin": "https://cad.onshape.com"}
        ) as websocket,
    ):
        response = client.post(
            "/tutorials/from-video",
            json={
                "video_url": "https://www.youtube.com/watch?v=wSBLOhIFz6s",
                "tutorial_id": "printer-clip",
            },
        )
        relayed = websocket.receive_json()

    assert response.status_code == 200
    assert relayed == response.json()
    assert captured["analysis_request"].video_url == "https://www.youtube.com/watch?v=wSBLOhIFz6s"
    planning_input = captured["planning_input"]
    assert planning_input["video_analysis"]["steps"] == analysis.model_dump(
        exclude_none=True
    )["steps"]
    assert planning_input["tutorial_metadata"]["voice"]["voice_id"] == "Rachel"
    plan = relayed["command"]["plan"]
    assert plan["tutorial_id"] == "printer-clip"
    assert plan["runtime_preferences"]["detailed_narration"] is False
    assert plan["steps"][0]["narration"]["concise"][
        "fal_elevenlabs_audio_url"
    ].startswith("https://audio.test/")

