from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.study_config import config_path, config_value, deliverable_path, step_path

PYTHON = ROOT / ".venv/bin/python"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)

STEP_COMMANDS = [
    [
        str(PYTHON),
        str(config_path("steps", "wash_extraction", "script")),
        "--dem",
        str(config_path("paths", "dem_filled")),
        "--accum",
        str(config_path("paths", "d8_flow_accum")),
        "--pointer",
        str(config_path("paths", "d8_pointer")),
        "--hazard",
        str(config_path("paths", "hazard_polygons")),
        "--local-aoi",
        str(config_path("paths", "local_aoi")),
        "--context-aoi",
        str(config_path("paths", "context_aoi")),
        "--outdir",
        str(step_path("wash_extraction", "outdir")),
        "--report",
        str(deliverable_path("wash_extraction_report")),
        "--thresholds",
        *[str(x) for x in config_value("study", "default_thresholds")],
    ],
    [
        str(PYTHON),
        str(config_path("steps", "parcel_overlay", "script")),
        "--streams",
        str(config_path("paths", "selected_streams")),
        "--parcel-boundary",
        str(config_path("paths", "parcel_boundary")),
        "--parcel-polygons",
        str(config_path("paths", "parcel_polygons")),
        "--hazard",
        str(config_path("paths", "hazard_polygons")),
        "--local-aoi",
        str(config_path("paths", "local_aoi")),
        "--context-aoi",
        str(config_path("paths", "context_aoi")),
        "--outdir",
        str(step_path("parcel_overlay", "outdir")),
        "--report",
        str(deliverable_path("parcel_overlay_report")),
        "--map-path",
        str(deliverable_path("parcel_overlay_map")),
    ],
    [
        str(PYTHON),
        str(config_path("steps", "fan_synthesis", "script")),
        "--dem",
        str(config_path("paths", "dem_filled")),
        "--slope",
        str(config_path("paths", "slope_degrees")),
        "--streams",
        str(config_path("paths", "selected_streams")),
        "--parcel-boundary",
        str(config_path("paths", "parcel_boundary")),
        "--parcel-polygons",
        str(config_path("paths", "parcel_polygons")),
        "--local-aoi",
        str(config_path("paths", "local_aoi")),
        "--context-aoi",
        str(config_path("paths", "context_aoi")),
        "--hazard",
        str(config_path("paths", "hazard_polygons")),
        "--outdir",
        str(step_path("fan_synthesis", "outdir")),
        "--report",
        str(deliverable_path("fan_synthesis_report")),
        "--map-path",
        str(deliverable_path("fan_synthesis_map")),
    ],
    [
        str(PYTHON),
        str(config_path("steps", "satellite_validation", "script")),
    ],
]


def verify_inputs() -> None:
    required = [
        config_path("paths", "dem_filled"),
        config_path("paths", "d8_flow_accum"),
        config_path("paths", "d8_pointer"),
        config_path("paths", "hazard_polygons"),
        config_path("paths", "local_aoi"),
        config_path("paths", "context_aoi"),
        config_path("paths", "parcel_boundary"),
        config_path("paths", "parcel_polygons"),
        config_path("paths", "selected_streams"),
        config_path("paths", "slope_degrees"),
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required inputs:\n- " + "\n- ".join(missing))


def run_step(command: list[str]) -> None:
    print(f"[pipeline] running: {' '.join(command)}")
    subprocess.run(command, check=True, cwd=ROOT)


def main() -> None:
    print(f"[pipeline] canonical CRS: {config_value('study', 'crs')}")
    print(f"[pipeline] final report: {deliverable_path('final_report')}")
    verify_inputs()
    for command in STEP_COMMANDS:
        run_step(command)
    print("[pipeline] complete")


if __name__ == "__main__":
    main()
