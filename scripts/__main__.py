from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Bootstrap: __main__.py is the top-level entry point; ensure repo root is importable.
_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[1]
if str(_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_ROOT_BOOTSTRAP))

from scripts.study_config import ROOT, config_path, config_value, study_config

PYTHON = ROOT / ".venv/bin/python"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)

STEPS = [
    "scripts.extract_washes",
    "scripts.parcel_overlay",
    "scripts.fan_synthesis",
    "scripts.satellite_validation",
]

RENDER_STEPS = [
    "scripts.render_wash_extraction",
    "scripts.render_parcel_overlay",
    "scripts.render_satellite_validation",
]

# Paths that are generated during the pipeline run, not pre-existing inputs.
_GENERATED_PATHS = {"d8_pointer"}


def verify_inputs() -> None:
    missing = []
    for name in study_config()["paths"]:
        if name in _GENERATED_PATHS:
            continue
        path = config_path("paths", name)
        if not path.exists():
            missing.append(str(path))
    if missing:
        raise FileNotFoundError("Missing required inputs:\n- " + "\n- ".join(missing))


def run_step(module: str) -> None:
    print(f"[pipeline] running: {module}")
    subprocess.run([str(PYTHON), "-m", module], check=True, cwd=ROOT)


def main() -> None:
    print(f"[pipeline] canonical CRS: {config_value('study', 'crs')}")
    print(f"[pipeline] steps: {STEPS}")
    verify_inputs()
    for module in STEPS:
        run_step(module)
    for module in RENDER_STEPS:
        run_step(module)
    print("[pipeline] complete")


if __name__ == "__main__":
    main()
