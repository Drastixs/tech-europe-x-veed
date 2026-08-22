import json

import pytest

from onshape_assist.analysis import fal, prompts
from onshape_assist.analysis.models import AnalysisRequest, AnalysisResult
from onshape_assist.analysis.pipeline import (
    AnalysisError,
    analyze_video,
    enforce_constraints,
    extract_json,
)

SAMPLE_PRIMARY = {
    "video": {
        "url": "https://www.youtube.com/watch?v=wSBLOhIFz6s",
        "application": "Onshape",
        "analyzed_start_ms": 259000,
        "analyzed_end_ms": 273000,
        "source_width": 1920,
        "source_height": 1080,
    },
    "full_transcript": {
        "verbatim_text": "Make sure no straight lines in the sketch.",
        "segments": [
            {
                "start_ms": 259000,
                "end_ms": 273000,
                "speaker": "instructor",
                "text": "Make sure no straight lines in the sketch.",
                "confidence": 0.92,
            }
        ],
    },
    "steps": [
        {
            "step_id": "open-revolve",
            "start_ms": 259000,
            "end_ms": 273000,
            "user_text": "Make sure no straight lines in the sketch.",
            "goal": "Open the Revolve feature.",
            "actions": [
                {
                    "sequence": 1,
                    "timestamp_ms": 264600,
                    "action_type": "click",
                    "mouse_button": "left",
                    "keys": [],
                    "typed_text": None,
                    "cursor_start": {"x": 812, "y": 731},
                    "cursor_end": {"x": 812, "y": 731},
                    "position_source": "inferred",
                    "ui_region": "active sketch modal",
                    "target_label": "OK",
                    "target_description": "The confirmation button.",
                    "icon_description": None,
                    "selected_object": None,
                    "visible_result": "The sketch modal closes.",
                    "confidence": 0.55,
                }
            ],
            "narration": "I'm confirming the sketch and opening Revolve.",
            "expected_end_state": "The Revolve dialog is open.",
            "uncertainties": [],
        }
    ],
}


def sample_for_url(video_url: str) -> dict:
    payload = json.loads(json.dumps(SAMPLE_PRIMARY))
    payload["video"]["url"] = video_url
    return payload


def make_runner(primary_payload, enrichment_text="A detailed UI description."):
    """Return an async runner that dispatches on the fal model id."""

    async def runner(model_id, arguments):
        if model_id == fal.ROUTER_VIDEO_MODEL:
            return {"output": json.dumps(primary_payload), "usage": {"total_tokens": 10}}
        if model_id == fal.VIDEO_UNDERSTANDING_MODEL:
            return {"output": enrichment_text}
        raise AssertionError(f"unexpected model id: {model_id}")

    return runner


def test_extract_json_handles_code_fences():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_handles_surrounding_prose():
    assert extract_json('Here you go:\n{"a": {"b": 2}}\nThanks!') == {"a": {"b": 2}}


def test_pipeline_parses_contract_for_direct_url():
    request = AnalysisRequest(video_url="https://media.example/clip.mp4")
    result = analyze_video(request, runner=make_runner(sample_for_url(request.video_url)))

    assert result.video.application == "Onshape"
    assert result.steps[0].actions[0].target_label == "OK"
    # A direct media URL supports the enrichment pass.
    assert result.scene_review == "A detailed UI description."


def test_youtube_skips_enrichment_pass():
    request = AnalysisRequest(video_url="https://www.youtube.com/watch?v=wSBLOhIFz6s")
    result = analyze_video(request, runner=make_runner(sample_for_url(request.video_url)))

    # YouTube links are not supported by video-understanding, so no scene review.
    assert result.scene_review is None
    assert result.steps[0].narration.startswith("I'm confirming")


def test_pipeline_rejects_missing_video_metadata_instead_of_backfilling():
    payload = {**SAMPLE_PRIMARY, "video": {"url": "", "application": ""}}
    request = AnalysisRequest(
        video_url="https://www.youtube.com/watch?v=abc",
        analysis_scope={"start_ms": 1000, "end_ms": 2000},
    )
    with pytest.raises(AnalysisError) as raised:
        analyze_video(request, runner=make_runner(payload))

    assert raised.value.detail["code"] == "contract_validation_failed"
    assert {item["path"] for item in raised.value.detail["violations"]} >= {
        "video.url",
        "video.application",
    }


def test_pipeline_rejects_malformed_action_instead_of_coercing_it():
    payload = sample_for_url("https://www.youtube.com/watch?v=abc")
    action = payload["steps"][0]["actions"][0]
    action["mouse_button"] = "null"
    action["target_label"] = "none"
    action["action_type"] = "double-click"

    request = AnalysisRequest(video_url="https://www.youtube.com/watch?v=abc")
    with pytest.raises(AnalysisError) as raised:
        analyze_video(request, runner=make_runner(payload))

    assert raised.value.detail["code"] == "contract_validation_failed"


@pytest.mark.parametrize(
    ("mutate", "expected_path"),
    [
        (
            lambda payload: payload["full_transcript"]["segments"].__setitem__(
                0, {**payload["full_transcript"]["segments"][0], "start_ms": 259001}
            ),
            "full_transcript.segments",
        ),
        (
            lambda payload: payload["steps"][0]["actions"][0].pop("cursor_end"),
            "steps[0].actions[0].cursor_end",
        ),
    ],
)
def test_pipeline_rejects_incomplete_transcript_or_pointer_evidence(mutate, expected_path):
    payload = sample_for_url("https://www.youtube.com/watch?v=abc")
    mutate(payload)

    with pytest.raises(AnalysisError) as raised:
        analyze_video(
            AnalysisRequest(video_url=payload["video"]["url"]), runner=make_runner(payload)
        )

    assert expected_path in {item["path"] for item in raised.value.detail["violations"]}


def test_scoped_prompt_injects_hard_time_bounds():
    # Prompt-building logic can be verified for free (no API call): a scoped
    # request must inject the numeric window and the hard in-range rule.
    request = AnalysisRequest(
        video_url="https://www.youtube.com/watch?v=abc",
        analysis_scope={"start_ms": 46000, "end_ms": 166000},
    )
    prompt = prompts.primary_user_prompt(request)

    assert "46000" in prompt and "166000" in prompt
    assert "HARD RULE" in prompt
    assert "wait" in prompt  # no-gap coverage instruction


def test_unscoped_prompt_requests_full_video():
    request = AnalysisRequest(video_url="https://www.youtube.com/watch?v=abc")
    prompt = prompts.primary_user_prompt(request)
    assert "ENTIRE video" in prompt


def test_system_prompt_correlates_audio_and_visual():
    request = AnalysisRequest(video_url="https://www.youtube.com/watch?v=abc")
    system = prompts.system_prompt(request)
    assert "AUDIO-VISUAL CORRELATION" in system
    assert "cross-reference" in system.lower()


def test_guardrail_drops_out_of_range_and_sorts_actions():
    payload = {
        "video": {"url": "u", "application": "Onshape"},
        "full_transcript": {
            "verbatim_text": "x",
            "segments": [
                {"start_ms": 1000, "end_ms": 1500, "text": "in"},
                {"start_ms": 9000, "end_ms": 9500, "text": "out"},
            ],
        },
        "steps": [
            {
                "step_id": "s1",
                "start_ms": 1000,
                "end_ms": 2000,
                "actions": [
                    {"sequence": 1, "timestamp_ms": 1800, "action_type": "click"},
                    {"sequence": 2, "timestamp_ms": 1200, "action_type": "click"},
                    {"sequence": 3, "timestamp_ms": 9000, "action_type": "click"},  # out
                ],
            }
        ],
    }
    request = AnalysisRequest(video_url="u", analysis_scope={"start_ms": 1000, "end_ms": 2000})
    result = enforce_constraints(AnalysisResult.model_validate(payload), request)

    actions = result.steps[0].actions
    assert [a.timestamp_ms for a in actions] == [1200, 1800]  # out-of-range dropped, sorted
    assert [a.sequence for a in actions] == [1, 2]  # re-sequenced
    # transcript segment fully outside the window is dropped
    assert len(result.full_transcript.segments) == 1


def test_guardrail_drops_step_that_loses_all_actions_but_keeps_narration_step():
    payload = {
        "video": {"url": "u"},
        "steps": [
            {  # had actions, all out of range -> dropped
                "step_id": "dropme",
                "start_ms": 8000,
                "end_ms": 9000,
                "actions": [{"timestamp_ms": 8500, "action_type": "click"}],
            },
            {  # intentionally action-free narration step -> kept
                "step_id": "keepme",
                "start_ms": 1000,
                "end_ms": 2000,
                "actions": [],
                "narration": "I explain the plan.",
            },
        ],
    }
    request = AnalysisRequest(video_url="u", analysis_scope={"start_ms": 1000, "end_ms": 2000})
    result = enforce_constraints(AnalysisResult.model_validate(payload), request)
    assert [s.step_id for s in result.steps] == ["keepme"]


def test_invalid_json_raises_analysis_error():
    async def bad_runner(model_id, arguments):
        return {"output": "not json at all"}

    request = AnalysisRequest(video_url="https://www.youtube.com/watch?v=abc")
    with pytest.raises(AnalysisError):
        analyze_video(request, runner=bad_runner)
