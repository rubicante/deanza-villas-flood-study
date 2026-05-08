"""Regenerate all canonical artifacts and diff against the pre-run state.

Safety-first: backs up canonical artifacts to data/_regenerate_backup/ before
running. After regeneration, diffs new outputs against backups. On failure,
restores from backup. On success with --update, deletes the backup.

Exit code 0 = all pass; 1 = any diff exceeds tolerance.

Tolerances:
  GeoJSON vectors: 1% area tolerance, 1% vertex count tolerance
  JSON stats: numeric values within 0.1%
  CSV: row count match, column names match
  HTML/MD: file exists and non-empty

Usage:
  python -m scripts.regenerate              # full run (~30+ min)
  python -m scripts.regenerate --skip-fetches  # skip network, verify local pipeline
  python -m scripts.regenerate --skip-satellite # skip earthaccess
  python -m scripts.regenerate --step extract_washes  # single step for debugging
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import geopandas as gpd

PROJECT = Path(__file__).resolve().parents[1]
BACKUP = PROJECT / "data" / "_regenerate_backup"
PYTHON = str(PROJECT / ".venv/bin/python")
REPO = str(PROJECT)

# Artifacts to back up (relative to repo root) — everything the pipeline can produce
BACKUP_ARTIFACTS: list[str] = []


def _collect_backup_artifacts() -> list[str]:
    """Collect all committed + pipeline-generated artifacts to back up."""
    artifacts: list[str] = []

    # Committed vectors
    for pattern in [
        "data/derived/vectors/*.geojson",
        "data/raw/sangis/*.geojson",
        "data/raw/fema/*.geojson",
        "outputs/maps/*.geojson",
    ]:
        for p in PROJECT.glob(pattern):
            artifacts.append(str(p.relative_to(PROJECT)))

    # Committed stats + reports
    for pattern in [
        "data/derived/2km_aoi/*.json",
        "data/derived/2km_aoi/*.csv",
        "outputs/reports/*.md",
        "outputs/maps/*.html",
    ]:
        for p in PROJECT.glob(pattern):
            artifacts.append(str(p.relative_to(PROJECT)))

    # Raw DEM (only committed raw file we regenerate)
    artifacts.append("data/raw/dem/deanza_villas_2km_1m_dem.tif")

    return sorted(set(artifacts))


# Tolerances
AREA_TOLERANCE = 0.01  # 1%
VERTEX_TOLERANCE = 0.01  # 1%
NUMERIC_TOLERANCE = 0.001  # 0.1%


@dataclass
class StepResult:
    name: str
    exit_code: int
    artifacts: list[ArtifactDiff] = field(default_factory=list)


@dataclass
class ArtifactDiff:
    path: str
    status: str  # "PASS", "FAIL", "SKIP"
    detail: str = ""


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

STEPS: list[dict[str, Any]] = [
    {"name": "fetch_parcels",     "skip": "skip_fetches",
     "cmd": [PYTHON, "scripts/fetch_parcels.py"]},
    {"name": "correct_parcel",    "skip": "",
     "cmd": [PYTHON, "scripts/correct_parcel.py"]},
    {"name": "build_aois",        "skip": "",
     "cmd": [PYTHON, "scripts/build_aois.py"]},
    {"name": "fetch_fema",        "skip": "skip_fetches",
     "cmd": [PYTHON, "scripts/fetch_fema.py", "--write"]},
    {"name": "fetch_huc12",       "skip": "skip_fetches",
     "cmd": [PYTHON, "scripts/fetch_huc12.py"]},
    {"name": "fetch_dem",         "skip": "skip_fetches",
     "cmd": [PYTHON, "-c",
             "from deliverable.fetch import fetch_dem; from pathlib import Path; "
             "fetch_dem(boundary=Path('data/derived/vectors/deanza_villas_2km_aoi.geojson'), "
             "resolution=1.0, crs='EPSG:5070', buffer_m=100, "
             "output=Path('data/raw/dem/deanza_villas_2km_1m_dem.tif'))"]},
    {"name": "henderson_watershed","skip": "skip_henderson",
     "cmd": [PYTHON, "-m", "deliverable._henderson", "watershed"]},
    {"name": "terrain_metrics",   "skip": "",
     "cmd": [PYTHON, "-m", "scripts.terrain_metrics"]},
    {"name": "extract_washes",    "skip": "",
     "cmd": [PYTHON, "-m", "scripts.extract_washes"]},
    {"name": "parcel_overlay",    "skip": "",
     "cmd": [PYTHON, "-m", "scripts.parcel_overlay"]},
    {"name": "fan_synthesis",     "skip": "",
     "cmd": [PYTHON, "-m", "scripts.fan_synthesis"]},
    {"name": "hand",              "skip": "",
     "cmd": [PYTHON, "-m", "scripts.hand"]},
    {"name": "curvature_tpi",     "skip": "",
     "cmd": [PYTHON, "-m", "scripts.curvature_tpi"]},
    {"name": "dri_roughness",     "skip": "",
     "cmd": [PYTHON, "-m", "scripts.dri_roughness_comparison"]},
    {"name": "satellite_validation","skip": "skip_satellite",
     "cmd": [PYTHON, "-m", "scripts.satellite_validation"]},
    {"name": "render_wash",       "skip": "",
     "cmd": [PYTHON, "-m", "scripts.render_wash_extraction"]},
    {"name": "render_parcel",     "skip": "",
     "cmd": [PYTHON, "-m", "scripts.render_parcel_overlay"]},
    {"name": "render_satellite",  "skip": "skip_satellite",
     "cmd": [PYTHON, "-m", "scripts.render_satellite_validation"]},
    {"name": "context_copies",    "skip": "",
     "cmd": ["bash", "-c",
             "cp data/raw/fema/nfhl_borrego_valley.geojson outputs/maps/ && "
             "cp data/derived/vectors/henderson_watershed_boundary.geojson outputs/maps/ && "
             "cp data/derived/vectors/borrego_palm_canyon_huc12.geojson outputs/maps/ && "
             "cp data/derived/vectors/deanza_community_bbox.geojson outputs/maps/"]},
]

# Artifacts to diff after each step
DIFF_MAP: dict[str, list[str]] = {
    "correct_parcel": [
        "data/raw/sangis/deanza_villas_parcel_polygons.geojson",
        "data/raw/sangis/deanza_villas_complex_boundary.geojson",
    ],
    "build_aois": [
        "data/derived/vectors/deanza_villas_2km_aoi.geojson",
        "data/derived/vectors/borrego_valley_context_8km_aoi.geojson",
    ],
    "fetch_fema": ["data/raw/fema/nfhl_borrego_valley.geojson"],
    "fetch_huc12": ["data/derived/vectors/borrego_palm_canyon_huc12.geojson"],
    "henderson_watershed": [
        "data/derived/vectors/henderson_watershed_boundary.geojson",
        "data/derived/vectors/henderson_watershed_boundary_5070.geojson",
    ],
    "extract_washes": [
        "data/derived/2km_aoi/deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.json",
        "data/derived/2km_aoi/deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.csv",
        "data/derived/2km_aoi/dinf_deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.json",
        "data/derived/2km_aoi/dinf_deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.csv",
        "data/derived/2km_aoi/deanza_villas_2km_1m_dem_filled_between_threshold_zones.json",
        "data/derived/2km_aoi/deanza_villas_2km_1m_dem_filled_between_threshold_zones.csv",
    ],
    "parcel_overlay": [
        "data/derived/2km_aoi/parcel_overlay_metrics.json",
        "data/derived/2km_aoi/parcel_overlay_metrics.csv",
    ],
    "fan_synthesis": [
        "data/derived/2km_aoi/fan_synthesis_stats.json",
        "data/derived/2km_aoi/fan_synthesis_stats.csv",
    ],
    "hand": ["data/derived/2km_aoi/hand_stats.json"],
    "curvature_tpi": ["data/derived/2km_aoi/curvature_tpi_stats.json"],
    "dri_roughness": [
        "data/derived/2km_aoi/dri_roughness_comparison_stats.json",
        "data/derived/vectors/dri_2015_fan_zones.geojson",
        "data/derived/vectors/dri_2015_fan_zones_epsg5070.geojson",
    ],
    "satellite_validation": [
        "data/derived/2km_aoi/satellite_validation_candidates.csv",
        "data/derived/2km_aoi/satellite_validation_candidates.json",
        "data/derived/2km_aoi/satellite_validation_selected.json",
    ],
    "render_wash": ["outputs/reports/wash_extraction.md"],
    "render_parcel": ["outputs/maps/parcel_overlay.html"],
    "render_satellite": [
        "outputs/reports/satellite_validation.md",
        "outputs/maps/satellite_validation.html",
    ],
    "context_copies": [
        "outputs/maps/nfhl_borrego_valley.geojson",
        "outputs/maps/henderson_watershed_boundary.geojson",
        "outputs/maps/borrego_palm_canyon_huc12.geojson",
        "outputs/maps/deanza_community_bbox.geojson",
    ],
}


# ---------------------------------------------------------------------------
# Diff functions
# ---------------------------------------------------------------------------


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT))
    except ValueError:
        return str(path)


def _compare_json_values(a: Any, b: Any, path: str) -> list[str]:
    """Recursively compare JSON values."""
    diffs: list[str] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k.startswith("fetched_") or k in ("metadata",):
                continue
            if k not in a:
                diffs.append(f"{path}.{k}: only in backup")
            elif k not in b:
                diffs.append(f"{path}.{k}: only in regenerated")
            else:
                diffs.extend(_compare_json_values(a[k], b[k], f"{path}.{k}"))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f"{path}: list len {len(a)}→{len(b)}")
        for i in range(min(len(a), len(b))):
            diffs.extend(_compare_json_values(a[i], b[i], f"{path}[{i}]"))
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a == 0 and b == 0:
            pass
        elif a == 0:
            if abs(b) > 1e-10:
                diffs.append(f"{path}: {a}→{b}")
        else:
            delta = abs(a - b) / abs(a)
            if delta > NUMERIC_TOLERANCE:
                diffs.append(f"{path}: {a}→{b} ({delta*100:+.2f}%)")
    elif a != b:
        diffs.append(f"{path}: {a!r}→{b!r}")
    return diffs


def diff_file(rel_path: str) -> ArtifactDiff:
    """Diff regenerated artifact against backup."""
    current = PROJECT / rel_path
    backup = BACKUP / rel_path
    suffix = Path(rel_path).suffix.lower()

    if not current.exists():
        return ArtifactDiff(rel_path, "FAIL", "not generated")
    if not backup.exists():
        return ArtifactDiff(rel_path, "PASS", "new artifact (no backup)")

    if suffix == ".geojson":
        try:
            c_gdf = gpd.read_file(backup)
            s_gdf = gpd.read_file(current)
        except Exception as e:
            return ArtifactDiff(rel_path, "FAIL", f"read error: {e}")
        if len(c_gdf) == 0 or len(s_gdf) == 0:
            return ArtifactDiff(rel_path, "FAIL", "empty GeoDataFrame")
        try:
            c_m = c_gdf.to_crs("EPSG:5070")
            s_m = s_gdf.to_crs("EPSG:5070")
        except Exception:
            c_m, s_m = c_gdf, s_gdf
        c_area = c_m.geometry.area.sum()
        s_area = s_m.geometry.area.sum()
        if c_area == 0:
            return ArtifactDiff(rel_path, "FAIL", "backup has zero area")
        ad = abs(s_area - c_area) / c_area
        c_v = sum(len(list(g.exterior.coords)) for g in c_m.geometry if g.geom_type == "Polygon")
        s_v = sum(len(list(g.exterior.coords)) for g in s_m.geometry if g.geom_type == "Polygon")
        vd = abs(s_v - c_v) / max(c_v, 1)
        ok = ad <= AREA_TOLERANCE and vd <= VERTEX_TOLERANCE
        try:
            inter = c_m.geometry.union_all().intersection(s_m.geometry.union_all()).area
            union = c_m.geometry.union_all().union(s_m.geometry.union_all()).area
            iou = inter / union if union > 0 else 0
        except Exception:
            iou = None
        detail = (f"area: {c_area/1e6:.3f}→{s_area/1e6:.3f} km² ({ad*100:+.2f}%), "
                  f"verts: {c_v}→{s_v} ({vd*100:+.1f}%)")
        if iou is not None:
            detail += f", IoU: {iou:.4f}"
        return ArtifactDiff(rel_path, "PASS" if ok else "FAIL", detail)

    elif suffix == ".json":
        try:
            c_data = json.loads(backup.read_text())
            s_data = json.loads(current.read_text())
        except Exception as e:
            return ArtifactDiff(rel_path, "FAIL", f"read error: {e}")
        diffs = _compare_json_values(c_data, s_data, "")
        if not diffs:
            return ArtifactDiff(rel_path, "PASS", "identical")
        return ArtifactDiff(rel_path, "FAIL",
                            f"{len(diffs)} diffs" if len(diffs) > 3
                            else "; ".join(diffs))

    elif suffix == ".csv":
        try:
            with open(backup) as f:
                c_rows = list(csv.reader(f))
            with open(current) as f:
                s_rows = list(csv.reader(f))
        except Exception as e:
            return ArtifactDiff(rel_path, "FAIL", f"read error: {e}")
        c_cols = c_rows[0] if c_rows else []
        s_cols = s_rows[0] if s_rows else []
        issues = []
        if len(c_rows) != len(s_rows):
            issues.append(f"rows: {len(c_rows)}→{len(s_rows)}")
        if c_cols != s_cols:
            issues.append("columns differ")
        if issues:
            return ArtifactDiff(rel_path, "FAIL", "; ".join(issues))
        return ArtifactDiff(rel_path, "PASS",
                            f"{len(c_rows)} rows, {len(c_cols)} cols match")

    elif suffix in (".html", ".md"):
        if not current.stat().st_size:
            return ArtifactDiff(rel_path, "FAIL", "empty")
        return ArtifactDiff(rel_path, "PASS",
                            f"exists ({current.stat().st_size:,} bytes)")

    elif suffix == ".tif":
        import rasterio
        try:
            with rasterio.open(backup) as c, rasterio.open(current) as s:
                if c.shape != s.shape:
                    return ArtifactDiff(rel_path, "FAIL",
                                        f"shape {c.shape}→{s.shape}")
                if str(c.crs) != str(s.crs):
                    return ArtifactDiff(rel_path, "FAIL", "CRS changed")
                return ArtifactDiff(rel_path, "PASS",
                                    f"{s.shape[1]}×{s.shape[0]}, CRS OK")
        except Exception as e:
            return ArtifactDiff(rel_path, "FAIL", str(e))

    return ArtifactDiff(rel_path, "SKIP", f"unknown type: {suffix}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate canonical artifacts and diff against pre-run state."
    )
    parser.add_argument("--skip-fetches", action="store_true")
    parser.add_argument("--skip-satellite", action="store_true")
    parser.add_argument("--skip-henderson", action="store_true")
    parser.add_argument("--step", type=str, help="Run only the named step.")
    args = parser.parse_args()

    # Load env
    env = os.environ.copy()
    env["PYTHONPATH"] = REPO
    env_path = PROJECT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")

    # Collect and back up artifacts
    BACKUP_ARTIFACTS = _collect_backup_artifacts()
    print(f"Backing up {len(BACKUP_ARTIFACTS)} artifacts to {BACKUP}...")
    if BACKUP.exists():
        shutil.rmtree(BACKUP)
    for rel in BACKUP_ARTIFACTS:
        src = PROJECT / rel
        dst = BACKUP / rel
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    results: list[StepResult] = []
    failures = 0

    for step_def in STEPS:
        name = step_def["name"]
        skip = step_def.get("skip", "")

        if skip == "skip_fetches" and args.skip_fetches:
            print(f"[{name}] SKIP (--skip-fetches)")
            continue
        if skip == "skip_satellite" and args.skip_satellite:
            print(f"[{name}] SKIP (--skip-satellite)")
            continue
        if skip == "skip_henderson" and args.skip_henderson:
            print(f"[{name}] SKIP (--skip-henderson)")
            continue
        if args.step and args.step != name:
            continue

        cmd = step_def["cmd"]
        print(f"[{name}] {' '.join(cmd[:4])}...")
        try:
            proc = subprocess.run(cmd, cwd=REPO, capture_output=True,
                                  text=True, timeout=600, env=env)
        except subprocess.TimeoutExpired:
            results.append(StepResult(name, -1))
            failures += 1
            print(f"  TIMEOUT")
            continue

        result = StepResult(name, proc.returncode)

        if proc.returncode != 0:
            failures += 1
            result.artifacts.append(
                ArtifactDiff(name, "FAIL",
                             f"exit {proc.returncode}: {proc.stderr[:200]}")
            )
            results.append(result)
            print(f"  FAIL (exit {proc.returncode})")
            continue

        # Diff artifacts for this step
        for rel_path in DIFF_MAP.get(name, []):
            ad = diff_file(rel_path)
            result.artifacts.append(ad)
            if ad.status == "FAIL":
                failures += 1
            print(f"  {ad.status:4s} {ad.path}: {ad.detail}")

        results.append(result)

    # Summary
    total_artifacts = sum(len(r.artifacts) for r in results)
    print(f"\n{'='*72}")
    print(f"  {total_artifacts} artifacts checked, {failures} failures")
    print(f"{'='*72}")

    if failures > 0:
        print("\nFAIL: regenerated outputs differ from backup.")
        print("Restoring backups...")
        for rel in BACKUP_ARTIFACTS:
            src = BACKUP / rel
            dst = PROJECT / rel
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        print("Restored.")
        if BACKUP.exists():
            shutil.rmtree(BACKUP)
        return 1

    print("\nPASS: all outputs match within tolerance.")
    print(f"Backup preserved at {BACKUP}.")
    print("Review and run with: rm -rf data/_regenerate_backup")
    return 0


if __name__ == "__main__":
    sys.exit(main())
