"""Command-line entry point for the video analyzer (``analyzectl``).

Examples::

    # Analyze a short range of a YouTube tutorial
    analyzectl --video-url https://www.youtube.com/watch?v=wSBLOhIFz6s \\
        --start-ms 259000 --end-ms 273000

    # Analyze from a request JSON file (matches the PRD input contract)
    analyzectl --input request.json --output analysis.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv
from pydantic import ValidationError

from onshape_assist.analysis import fal
from onshape_assist.analysis.models import AnalysisRequest
from onshape_assist.analysis.pipeline import AnalysisError, analyze_video


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analyzectl",
        description="Analyze an Onshape tutorial video into timestamped actions and narration.",
    )
    parser.add_argument("--input", help="Path to a request JSON file (PRD input contract).")
    parser.add_argument("--video-url", help="Video URL (overrides --input).")
    parser.add_argument("--application", default="Onshape")
    parser.add_argument("--start-ms", type=int, help="Optional analysis start in ms.")
    parser.add_argument("--end-ms", type=int, help="Optional analysis end in ms.")
    parser.add_argument("--output-language", default="en")
    parser.add_argument(
        "--model",
        default=fal.DEFAULT_GEMINI_MODEL,
        help="Underlying LLM for the OpenRouter video router.",
    )
    parser.add_argument(
        "--no-enrichment",
        action="store_true",
        help="Skip the fal-ai/video-understanding enrichment pass.",
    )
    parser.add_argument("--output", help="Write the analysis JSON here (default: stdout).")
    return parser


def request_from_args(args: argparse.Namespace) -> AnalysisRequest:
    data: dict = {}
    if args.input:
        with open(args.input, encoding="utf-8") as handle:
            data = json.load(handle)
    if args.video_url:
        data["video_url"] = args.video_url
    if args.application:
        data.setdefault("application", args.application)
    if args.output_language:
        data.setdefault("output_language", args.output_language)
    if args.start_ms is not None and args.end_ms is not None:
        data["analysis_scope"] = {"start_ms": args.start_ms, "end_ms": args.end_ms}
    return AnalysisRequest.model_validate(data)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Load FAL_KEY (and friends) from a local .env if present; never overrides
    # values already set in the environment.
    load_dotenv()

    if not args.input and not args.video_url:
        parser.error("provide --video-url or --input")

    if not os.environ.get("FAL_KEY"):
        print("analyzectl: FAL_KEY is not set in the environment.", file=sys.stderr)
        return 2

    try:
        request = request_from_args(args)
    except (ValidationError, json.JSONDecodeError, OSError) as exc:
        print(f"analyzectl: invalid request: {exc}", file=sys.stderr)
        return 2

    try:
        result = analyze_video(
            request,
            gemini_model=args.model,
            with_enrichment=not args.no_enrichment,
        )
    except AnalysisError as exc:
        print(f"analyzectl: analysis failed: {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(result.model_dump(), indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
        print(f"analyzectl: wrote analysis to {args.output}", file=sys.stderr)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
