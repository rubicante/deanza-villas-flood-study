from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.study_config import TARGET_CRS, config_path, config_value, manifest_value

PYTHON = ROOT / ".venv/bin/python"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)

PHASE_COMMANDS = [
    [
        str(PYTHON),
        "scripts/phase2_extract_washes.py",
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
        str(config_path("outputs", "phase2_outdir")),
        "--report-dir",
        str(ROOT / "outputs/reports"),
        "--thresholds",
        *[str(x) for x in config_value("study", "default_thresholds")],
    ],
    [
        str(PYTHON),
        "scripts/phase3_parcel_overlay.py",
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
        str(config_path("outputs", "phase3_parcel_outdir")),
        "--report-dir",
        str(ROOT / "outputs/reports"),
        "--map-path",
        str(config_path("outputs", "phase3_parcel_map")),
    ],
    [
        str(PYTHON),
        "scripts/phase3_fan_synthesis.py",
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
        str(config_path("outputs", "phase3_fan_outdir")),
        "--report",
        str(config_path("outputs", "phase3_fan_report")),
        "--map-path",
        str(config_path("outputs", "phase3_fan_map")),
    ],
    [
        str(PYTHON),
        "scripts/phase4_satellite_validation.py",
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


def run_phase(command: list[str]) -> None:
    print(f"[pipeline_v2] running: {' '.join(command)}")
    subprocess.run(command, check=True, cwd=ROOT)


def main() -> None:
    print(f"[pipeline_v2] canonical CRS: {TARGET_CRS}")
    print(f"[pipeline_v2] final report: {manifest_value('canonical_deliverables', 'final_report')}")
    verify_inputs()
    for command in PHASE_COMMANDS:
        run_phase(command)
    print("[pipeline_v2] complete")


if __name__ == "__main__":
    main()
