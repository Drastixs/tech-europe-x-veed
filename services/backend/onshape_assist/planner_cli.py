"""Command-line entry point for producing an executable tutorial plan."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from onshape_assist.app import TutorialPlan, TutorialPlanningRequest
from onshape_assist.narration import (
    NarrationConfigurationError,
    NarrationError,
    enrich_plan_narration,
)
from onshape_assist.planner import OpenAIPlanner, PlannerError, error_envelope


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plannerctl",
        description="Convert video-analysis JSON into an executable Onshape tutorial plan.",
    )
    parser.add_argument("--input", required=True, help="Path to a tutorial planning request JSON file.")
    parser.add_argument("--output", help="Write the tutorial plan JSON here (default: stdout).")
    return parser


async def create_plan(request: TutorialPlanningRequest) -> TutorialPlan:
    planning_input = {
        "video_analysis": request.video_analysis,
        "tutorial_metadata": {
            "tutorial_id": request.tutorial_id,
            "application": request.application,
            "output_language": request.output_language,
            "runtime_preferences": request.runtime_preferences.model_dump(),
            "voice": request.voice.model_dump(),
        },
    }
    generated = await OpenAIPlanner().generate(
        input_payload=planning_input,
        schema=TutorialPlan.model_json_schema(),
    )
    plan = TutorialPlan.model_validate(generated).model_copy(
        update={
            "tutorial_id": request.tutorial_id,
            "application": request.application,
            "output_language": request.output_language,
            "runtime_preferences": request.runtime_preferences,
            "voice": request.voice,
        }
    )
    for tutorial_step in plan.steps:
        for variant_name in ("concise", "detailed"):
            variant = getattr(tutorial_step.narration, variant_name)
            variant.fal_elevenlabs_audio_url = f"pending://tts/{tutorial_step.step_id}/{variant_name}"
            variant.duration_ms = 0
    return TutorialPlan.model_validate(await enrich_plan_narration(plan))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    try:
        with open(args.input, encoding="utf-8") as handle:
            payload = json.load(handle)
        request_payload = payload.get("request", payload) if isinstance(payload, dict) else payload
        request = TutorialPlanningRequest.model_validate(request_payload)
        plan = asyncio.run(create_plan(request))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(json.dumps(error_envelope("invalid_request", str(exc))), file=sys.stderr)
        return 2
    except PlannerError as exc:
        print(json.dumps(exc.envelope()), file=sys.stderr)
        return 1
    except NarrationConfigurationError as exc:
        print(json.dumps(error_envelope("narration_configuration_error", str(exc))), file=sys.stderr)
        return 1
    except NarrationError as exc:
        print(json.dumps(error_envelope("narration_error", str(exc))), file=sys.stderr)
        return 1

    rendered = json.dumps(plan.model_dump(), indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(f"{rendered}\n", encoding="utf-8")
        print(f"plannerctl: wrote tutorial plan to {args.output}", file=sys.stderr)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
