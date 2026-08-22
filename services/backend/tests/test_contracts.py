import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from onshape_assist.contracts import RuntimeContractBundle

FIXTURE = (
    Path(__file__).resolve().parents[3] / "contracts/fixtures/revolve-from-sketch-1.runtime-v1.json"
)


def test_runtime_contract_fixture_is_accepted():
    bundle = RuntimeContractBundle.model_validate_json(FIXTURE.read_text())

    assert bundle.contract_version == 1
    assert bundle.tutorial_plan.steps[0].actions[0].preferred_activation == "dom"
    assert bundle.validation_outcome.outcome == "correct"


def test_runtime_contract_rejects_unknown_outcomes():
    payload = json.loads(FIXTURE.read_text())
    payload["validation_outcome"]["outcome"] = "maybe_correct"

    with pytest.raises(ValidationError):
        RuntimeContractBundle.model_validate(payload)
