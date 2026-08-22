import json

import pytest

from onshape_assist.analysis import fal, prompts
from onshape_assist.analysis.models import AnalysisRequest
from onshape_assist.analysis.pipeline import (
    AnalysisError,
    analyze_video,
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
                "end_ms": 264500,
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
    result = analyze_video(request, runner=make_runner(SAMPLE_PRIMARY))

    assert result.video.application == "Onshape"
    assert result.steps[0].actions[0].target_label == "OK"
    # A direct media URL supports the enrichment pass.
    assert result.scene_review == "A detailed UI description."


def test_youtube_skips_enrichment_pass():
    request = AnalysisRequest(video_url="https://www.youtube.com/watch?v=wSBLOhIFz6s")
    result = analyze_video(request, runner=make_runner(SAMPLE_PRIMARY))

    # YouTube links are not supported by video-understanding, so no scene review.
    assert result.scene_review is None
    assert result.steps[0].narration.startswith("I'm confirming")


def test_video_meta_backfilled_from_request():
    payload = {**SAMPLE_PRIMARY, "video": {"url": "", "application": ""}}
    request = AnalysisRequest(
        video_url="https://www.youtube.com/watch?v=abc",
        analysis_scope={"start_ms": 1000, "end_ms": 2000},
    )
    result = analyze_video(request, runner=make_runner(payload))

    assert result.video.url == "https://www.youtube.com/watch?v=abc"
    assert result.video.analyzed_start_ms == 1000
    assert result.video.analyzed_end_ms == 2000


def test_stringy_null_fields_are_coerced():
    # Models sometimes emit the literal string "null" instead of JSON null.
    payload = json.loads(json.dumps(SAMPLE_PRIMARY))
    action = payload["steps"][0]["actions"][0]
    action["mouse_button"] = "null"
    action["target_label"] = "none"
    action["action_type"] = "double-click"

    request = AnalysisRequest(video_url="https://www.youtube.com/watch?v=abc")
    result = analyze_video(request, runner=make_runner(payload))

    coerced = result.steps[0].actions[0]
    assert coerced.mouse_button is None
    assert coerced.target_label is None
    assert coerced.action_type == "double_click"


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


def test_invalid_json_raises_analysis_error():
    async def bad_runner(model_id, arguments):
        return {"output": "not json at all"}

    request = AnalysisRequest(video_url="https://www.youtube.com/watch?v=abc")
    with pytest.raises(AnalysisError):
        analyze_video(request, runner=bad_runner)
