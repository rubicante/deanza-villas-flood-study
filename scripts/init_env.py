"""Minimal project bootstrap for De Anza Villas flood study.

Loads the project-local .env file into os.environ.
No external dependencies.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


def load_env(path: Path = ENV_PATH) -> dict[str, str]:
    """Load KEY=VALUE pairs from a .env file into os.environ.

    Comments and blank lines are ignored. Existing environment variables are
    left untouched.
    """
    if not path.exists():
        raise FileNotFoundError(path)

    loaded: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        loaded[key] = value
        os.environ.setdefault(key, value)
    return loaded


if __name__ == "__main__":
    loaded = load_env()
    print(f"loaded {len(loaded)} variables from {ENV_PATH}")
