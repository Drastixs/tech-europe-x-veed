from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_URL = "http://127.0.0.1:8000/commands"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = command_from_args(args)
    request = urllib.request.Request(
        args.url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            print(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        print(f"overlayctl: could not reach relay at {args.url}: {exc}", file=sys.stderr)
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="overlayctl")
    parser.add_argument("--url", default=DEFAULT_URL)
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("show")
    subcommands.add_parser("hide")
    subcommands.add_parser("click")
    subcommands.add_parser("left")
    subcommands.add_parser("right")
    subcommands.add_parser("arm")
    subcommands.add_parser("disarm")

    move = subcommands.add_parser("move")
    move.add_argument("x", type=int)
    move.add_argument("y", type=int)
    move.add_argument("--duration-ms", type=int, default=420)
    return parser


def command_from_args(args: argparse.Namespace) -> dict[str, Any]:
    match args.command:
        case "show" | "hide" | "click":
            return {"type": args.command}
        case "left" | "right":
            return {"type": "navigate", "direction": args.command}
        case "arm":
            return {"type": "arm_takeover"}
        case "disarm":
            return {"type": "disarm_takeover"}
        case "move":
            return {
                "type": "move",
                "x": args.x,
                "y": args.y,
                "duration_ms": args.duration_ms,
            }
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
