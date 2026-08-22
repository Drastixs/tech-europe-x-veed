import json

import httpx
import pytest

from onshape_assist.onshape import OnshapeClient, OnshapeError, OnshapeTarget

TARGET = OnshapeTarget(document_id="document", workspace_id="workspace", element_id="element")


def feature_list(*feature_types: str, rollback_index: int = 1):
    return {
        "rollbackIndex": rollback_index,
        "features": [
            {"featureId": f"id-{index}", "featureType": feature_type, "name": feature_type}
            for index, feature_type in enumerate(feature_types)
        ],
    }


def test_capture_baseline_uses_current_microversion_features_and_parts():
    client, calls = client_for(
        microversions=["baseline"],
        feature_lists=[feature_list("newSketch", rollback_index=3)],
        part_lists=[[part("part-1")]],
    )

    snapshot = client.snapshot(TARGET)

    assert snapshot.microversion_id == "baseline"
    assert snapshot.features.rollback_index == 3
    assert snapshot.geometry.part_ids == ("part-1",)
    assert calls == [
        "/api/documents/d/document/w/workspace/currentmicroversion",
        "/api/partstudios/d/document/w/workspace/e/element/features",
        "/api/parts/d/document/w/workspace/e/element",
    ]


def test_restore_refuses_when_document_changed_after_demo():
    client, calls = client_for(
        microversions=["baseline", "learner-edit", "learner-edit"],
        feature_lists=[feature_list("newSketch"), feature_list("newSketch")],
        part_lists=[[part("part-1")], [part("part-1")]],
    )
    baseline = client.snapshot(TARGET)

    result = client.restore_baseline(baseline, expected_microversion_id="demo")

    assert result.outcome == "concurrent_edit"
    assert "/api/partstudios/d/document/w/workspace/e/element/features/rollback" not in calls


def test_restore_moves_rollback_bar_and_confirms_baseline_content():
    client, calls = client_for(
        microversions=["baseline", "demo", "restored"],
        feature_lists=[
            feature_list("newSketch", rollback_index=1),
            feature_list("newSketch", rollback_index=1),
        ],
        part_lists=[[part("part-1")], [part("part-1")]],
    )
    baseline = client.snapshot(TARGET)

    result = client.restore_baseline(baseline, expected_microversion_id="demo")

    assert result.outcome == "restored"
    assert "/api/partstudios/d/document/w/workspace/e/element/features/rollback" in calls


@pytest.mark.parametrize(
    ("microversions", "feature_lists", "expected_type", "outcome"),
    [
        (["baseline", "learner"], [feature_list("newSketch"), feature_list("newSketch", "extrude")], "extrude", "correct"),
        (["baseline", "learner"], [feature_list("newSketch"), feature_list("newSketch", "revolve")], "extrude", "wrong_tool"),
        (
            ["baseline", "baseline"],
            [feature_list("newSketch"), feature_list("newSketch")],
            "extrude",
            "no_committed_change",
        ),
    ],
)
def test_validate_attempt_distinguishes_expected_wrong_and_missing_changes(
    microversions, feature_lists, expected_type, outcome
):
    part_lists = [[part("part-1")], [part("part-1")]]
    client, _ = client_for(
        microversions=microversions,
        feature_lists=feature_lists,
        part_lists=part_lists,
    )
    baseline = client.snapshot(TARGET)

    result = client.validate_attempt(baseline, expected_feature_type=expected_type)

    assert result.outcome == outcome


def test_target_parses_a_real_workspace_url():
    target = OnshapeTarget.from_document_url(
        "https://cad.onshape.com/documents/document/w/workspace/e/element"
    )

    assert target == TARGET


def test_target_rejects_versions_that_cannot_be_rolled_back():
    with pytest.raises(OnshapeError, match="workspace URL"):
        OnshapeTarget.from_document_url(
            "https://cad.onshape.com/documents/document/v/version/e/element"
        )


def test_client_wraps_network_failures_with_an_onshape_error():
    def unavailable(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    client = OnshapeClient(
        "access",
        "secret",
        base_url="https://onshape.test/api",
        client=httpx.Client(transport=httpx.MockTransport(unavailable)),
    )

    with pytest.raises(OnshapeError, match="could not be reached"):
        client.snapshot(TARGET)


def client_for(*, microversions, feature_lists, part_lists):
    queues = {
        "currentmicroversion": iter(microversions),
        "/features": iter(feature_lists),
        "/parts/": iter(part_lists),
    }
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        path = request.url.path
        if path.endswith("currentmicroversion"):
            return httpx.Response(200, json={"microversionId": next(queues["currentmicroversion"])})
        if path.endswith("/features/rollback"):
            assert json.loads(request.content) == {"rollbackIndex": 1}
            return httpx.Response(200, json={})
        if path.endswith("/features"):
            return httpx.Response(200, json=next(queues["/features"]))
        if "/parts/" in path:
            return httpx.Response(200, json=next(queues["/parts/"]))
        raise AssertionError(path)

    return (
        OnshapeClient(
            "access",
            "secret",
            base_url="https://onshape.test/api",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ),
        calls,
    )


def part(part_id: str):
    return {"partId": part_id, "name": part_id, "bodyType": "solid", "isClosed": True}
