from __future__ import annotations

import json
from pathlib import Path

from onshape_assist import planner_cli
from onshape_assist.app import TutorialPlan, TutorialPlanningRequest
from onshape_assist.planner import PlannerError

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "revolve-from-sketch-1.analysis-to-plan-v1.json"
)


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_canonical_analysis_to_plan_fixture_uses_the_live_protocol():
    fixture = load_fixture()

    assert fixture["version"] == "tutorial-planning-fixture/v1"
    request = TutorialPlanningRequest.model_validate(fixture["request"])
    plan = TutorialPlan.model_validate(fixture["plan"])

    assert request.tutorial_id == plan.tutorial_id == "revolve-from-sketch-1"
    assert plan.steps[0].dynamic_corrections.target_relocated
    assert plan.steps[0].actions[0].fallback_activation == "cdp"


def test_planner_cli_creates_and_writes_a_plan_from_the_canonical_request(monkeypatch, tmp_path):
    fixture = load_fixture()
    output = tmp_path / "plan.json"
    expected_plan = TutorialPlan.model_validate(fixture["plan"])

    class FakePlanner:
        async def generate(self, **_: object) -> dict:
            return fixture["plan"]

    async def no_op_enrichment(plan: TutorialPlan) -> TutorialPlan:
        return plan

    monkeypatch.setattr(planner_cli, "OpenAIPlanner", FakePlanner)
    monkeypatch.setattr(planner_cli, "enrich_plan_narration", no_op_enrichment)

    assert planner_cli.main(["--input", str(FIXTURE), "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == expected_plan.model_dump()


def test_planner_cli_writes_versioned_errors(monkeypatch, tmp_path, capsys):
    source = tmp_path / "request.json"
    source.write_text(json.dumps(load_fixture()["request"]), encoding="utf-8")

    async def fail(_: TutorialPlanningRequest) -> TutorialPlan:
        raise PlannerError("provider unavailable", status_code=503, code="provider_unavailable")

    monkeypatch.setattr(planner_cli, "create_plan", fail)

    assert planner_cli.main(["--input", str(source)]) == 1
    assert json.loads(capsys.readouterr().err) == {
        "version": "tutorial-planner-error/v1",
        "code": "provider_unavailable",
        "message": "provider unavailable",
    }
