from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask
from whitebox.whitebox_tools import WhiteboxTools

from scripts.init_env import load_env
from scripts.study_config import TARGET_CRS, config_path
from scripts.study_utils import ensure_crs, safe_write_json

DEM_PATH = config_path("paths", "dem_filled")
LOCAL_AOI_PATH = config_path("paths", "local_aoi")
PARCEL_BOUNDARY_PATH = config_path("paths", "parcel_boundary")
TERRAIN_OUTDIR = config_path("paths", "terrain_outdir")
PROFILE_CURVATURE_PATH = config_path("paths", "profile_curvature")
TPI_PATH = config_path("paths", "tpi")
TPI_SCALE_PATH = config_path("paths", "tpi_scale")
STATS_JSON_PATH = config_path("paths", "curvature_tpi_stats")
METRIC_OUTDIR = STATS_JSON_PATH.parent


def _remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def _clean_number(value: float) -> float | None:
    if math.isfinite(value):
        return float(value)
    return None


def raster_zone_stats(raster_path: Path, geom, zone_name: str) -> dict[str, object]:
    with rasterio.open(raster_path) as ds:
        arr, _ = mask(ds, [geom], crop=True, filled=False)
        data = np.array(arr[0].filled(np.nan), dtype="float64")
        data = data[np.isfinite(data)]

    if data.size == 0:
        return {
            "zone": zone_name,
            "valid_cells": 0,
            "min": None,
            "mean": None,
            "max": None,
        }

    return {
        "zone": zone_name,
        "valid_cells": int(data.size),
        "min": _clean_number(float(np.min(data))),
        "mean": _clean_number(float(np.mean(data))),
        "max": _clean_number(float(np.max(data))),
    }


def ensure_curvature_and_tpi() -> str:
    load_env()
    TERRAIN_OUTDIR.mkdir(parents=True, exist_ok=True)
    METRIC_OUTDIR.mkdir(parents=True, exist_ok=True)

    dem_path = DEM_PATH.resolve()
    profile_curvature_path = PROFILE_CURVATURE_PATH.resolve()
    tpi_path = TPI_PATH.resolve()
    tpi_scale_path = TPI_SCALE_PATH.resolve()

    wbt = WhiteboxTools()
    wbt.set_working_dir(str(TERRAIN_OUTDIR.resolve()))
    wbt.set_verbose_mode(False)

    _remove_if_exists(profile_curvature_path)
    wbt.profile_curvature(str(dem_path), str(profile_curvature_path))

    _remove_if_exists(tpi_path)
    _remove_if_exists(tpi_scale_path)
    if hasattr(wbt, "max_elevation_deviation"):
        tpi_method = "max_elevation_deviation"
        # Whitebox MaxElevationDeviation emits a magnitude raster plus the scale
        # at which that local topographic-position signal was strongest. The
        # magnitude raster is the canonical TPI-like output requested here.
        wbt.max_elevation_deviation(
            str(dem_path),
            str(tpi_path),
            str(tpi_scale_path),
            min_scale=1,
            max_scale=25,
            step=5,
        )
    else:
        tpi_method = "relative_topographic_position"
        wbt.relative_topographic_position(str(dem_path), str(tpi_path))

    required = [profile_curvature_path, tpi_path]
    for path in required:
        if not path.exists():
            raise FileNotFoundError(f"Expected output was not created: {path}")
    if tpi_method == "max_elevation_deviation" and not tpi_scale_path.exists():
        raise FileNotFoundError(f"Expected TPI scale output was not created: {tpi_scale_path}")

    return tpi_method


def build_stats(tpi_method: str) -> dict[str, object]:
    local_aoi = ensure_crs(gpd.read_file(LOCAL_AOI_PATH), TARGET_CRS)
    parcel_boundary = ensure_crs(gpd.read_file(PARCEL_BOUNDARY_PATH), TARGET_CRS)

    zones = {
        "local_aoi": local_aoi.geometry.union_all(),
        "parcel": parcel_boundary.geometry.union_all(),
    }
    rasters = {
        "profile_curvature": PROFILE_CURVATURE_PATH.resolve(),
        "tpi": TPI_PATH.resolve(),
    }

    zone_stats: list[dict[str, object]] = []
    for metric_name, raster_path in rasters.items():
        for zone_name, geom in zones.items():
            row = raster_zone_stats(raster_path, geom, zone_name)
            row["metric"] = metric_name
            row["raster"] = str(raster_path)
            zone_stats.append(row)

    stats = {
        "inputs": {
            "dem_filled": str(DEM_PATH.resolve()),
            "local_aoi": str(LOCAL_AOI_PATH.resolve()),
            "parcel_boundary": str(PARCEL_BOUNDARY_PATH.resolve()),
        },
        "outputs": {
            "profile_curvature": str(PROFILE_CURVATURE_PATH.resolve()),
            "tpi": str(TPI_PATH.resolve()),
            "tpi_scale": str(TPI_SCALE_PATH.resolve()) if TPI_SCALE_PATH.exists() else None,
            "stats_json": str(STATS_JSON_PATH.resolve()),
        },
        "tpi_method": tpi_method,
        "tpi_parameters": (
            {"min_scale": 1, "max_scale": 25, "step": 5}
            if tpi_method == "max_elevation_deviation"
            else {"filterx": 11, "filtery": 11}
        ),
        "zones": zone_stats,
    }
    safe_write_json(stats, STATS_JSON_PATH)
    return stats


def print_summary(stats: dict[str, object]) -> None:
    outputs = stats["outputs"]
    print(f"profile_curvature: {outputs['profile_curvature']}")
    print(f"tpi:               {outputs['tpi']}")
    if outputs.get("tpi_scale"):
        print(f"tpi_scale:         {outputs['tpi_scale']}")
    print(f"stats_json:        {outputs['stats_json']}")
    print(f"tpi_method:        {stats['tpi_method']}")
    print("zone statistics:")
    for row in stats["zones"]:
        print(
            f"  {row['metric']} | {row['zone']}: "
            f"valid_cells={row['valid_cells']} "
            f"min={row['min']} mean={row['mean']} max={row['max']}"
        )


def main() -> None:
    tpi_method = ensure_curvature_and_tpi()
    stats = build_stats(tpi_method)
    print_summary(stats)


if __name__ == "__main__":
    main()
