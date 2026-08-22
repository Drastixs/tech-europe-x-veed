from __future__ import annotations

import os
from pathlib import Path


def load_backend_env(path: Path | None = None) -> None:
    """Load simple KEY=VALUE entries without replacing the process environment."""
    env_path = path or Path(__file__).resolve().parent.parent / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "a").isalnum() or key[0].isdigit():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)
