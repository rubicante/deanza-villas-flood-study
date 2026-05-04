from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask
from whitebox.whitebox_tools import WhiteboxTools

from scripts.init_env import load_env
from scripts.study_config import (
    config_path,
    step_path,
)
from scripts.study_utils import ensure_crs

DEM_PATH = config_path("paths", "dem_filled")
SLOPE_PATH = config_path("paths", "slope_degrees")
STREAMS_PATH = config_path("paths", "selected_streams")
PARCEL_BOUNDARY_PATH = config_path("paths", "parcel_boundary")
LOCAL_AOI_PATH = config_path("paths", "local_aoi")
CONTEXT_AOI_PATH = config_path("paths", "context_aoi")
ROUGH_MAG_PATH = config_path("paths", "roughness_magnitude")
ROUGH_SCALE_PATH = config_path("paths", "roughness_scale")
OUTDIR = step_path("fan_synthesis", "outdir")


@dataclass
class AreaStats:
    area_name: str
    area_m2: float
    area_km2: float
    valid_cells: int
    elev_min: float
    elev_p5: float
    elev_mean: float
    elev_p95: float
    elev_max: float
    elev_std: float
    relief_p95_p5_m: float
    relief_max_min_m: float
    slope_mean_deg: float
    slope_p95_deg: float
    slope_std_deg: float
    rough_mean_m: float
    rough_p95_m: float
    rough_std_m: float
    stream_length_m: float
    stream_density_m_per_km2: float


def _raster_stats(path: Path, geom) -> dict[str, float | int]:
    with rasterio.open(path) as ds:
        arr, _ = mask(ds, [geom], crop=True, filled=False)
        data = np.array(arr[0].filled(np.nan), dtype="float64")
        data = data[np.isfinite(data)]
        return {
            "valid_cells": int(data.size),
            "min": float(np.min(data)),
            "p5": float(np.percentile(data, 5)),
            "mean": float(np.mean(data)),
            "p95": float(np.percentile(data, 95)),
            "max": float(np.max(data)),
            "std": float(np.std(data)),
        }


def _stream_stats(streams: gpd.GeoDataFrame, geom) -> float:
    inside = streams[streams.intersects(geom)].copy()
    return float(inside.geometry.intersection(geom).length.sum())


def ensure_roughness(dem_path: Path, rough_mag: Path, rough_scale: Path) -> None:
    if rough_mag.exists() and rough_scale.exists():
        return
    load_env()
    rough_mag.parent.mkdir(parents=True, exist_ok=True)
    wbt = WhiteboxTools()
    wbt.set_working_dir(str(rough_mag.parent))
    wbt.set_verbose_mode(False)
    wbt.multiscale_roughness(str(dem_path), str(rough_mag), str(rough_scale), max_scale=25, min_scale=1, step=5)


def build_area_stats(
    area_name: str,
    geom,
    dem_path: Path,
    slope_path: Path,
    rough_mag_path: Path,
    streams: gpd.GeoDataFrame,
) -> AreaStats:
    dem = _raster_stats(dem_path, geom)
    slope = _raster_stats(slope_path, geom)
    rough = _raster_stats(rough_mag_path, geom)
    area_m2 = float(geom.area)
    stream_length_m = _stream_stats(streams, geom)
    return AreaStats(
        area_name=area_name,
        area_m2=area_m2,
        area_km2=area_m2 / 1e6,
        valid_cells=int(dem["valid_cells"]),
        elev_min=dem["min"],
        elev_p5=dem["p5"],
        elev_mean=dem["mean"],
        elev_p95=dem["p95"],
        elev_max=dem["max"],
        elev_std=dem["std"],
        relief_p95_p5_m=dem["p95"] - dem["p5"],
        relief_max_min_m=dem["max"] - dem["min"],
        slope_mean_deg=slope["mean"],
        slope_p95_deg=slope["p95"],
        slope_std_deg=slope["std"],
        rough_mean_m=rough["mean"],
        rough_p95_m=rough["p95"],
        rough_std_m=rough["std"],
        stream_length_m=stream_length_m,
        stream_density_m_per_km2=(stream_length_m / (area_m2 / 1e6)) if area_m2 else 0.0,
    )


def main() -> None:
    load_env()

    ensure_roughness(DEM_PATH, ROUGH_MAG_PATH, ROUGH_SCALE_PATH)

    # Read vectors once; pass GeoDataFrames to all downstream functions.
    streams = ensure_crs(gpd.read_file(STREAMS_PATH))
    parcel_boundary = ensure_crs(gpd.read_file(PARCEL_BOUNDARY_PATH))
    local_aoi = ensure_crs(gpd.read_file(LOCAL_AOI_PATH))
    context_aoi = ensure_crs(gpd.read_file(CONTEXT_AOI_PATH))

    parcel_geom = parcel_boundary.geometry.iloc[0]
    local_geom = local_aoi.geometry.iloc[0]
    context_geom = context_aoi.geometry.iloc[0]

    stats = [
        asdict(build_area_stats("parcel", parcel_geom, DEM_PATH, SLOPE_PATH, ROUGH_MAG_PATH, streams)),
        asdict(build_area_stats("local_aoi", local_geom, DEM_PATH, SLOPE_PATH, ROUGH_MAG_PATH, streams)),
        asdict(build_area_stats("context_aoi", context_geom, DEM_PATH, SLOPE_PATH, ROUGH_MAG_PATH, streams)),
    ]
    stats_df = pd.DataFrame(stats)

    OUTDIR.mkdir(parents=True, exist_ok=True)
    stats_csv = OUTDIR / "fan_synthesis_stats.csv"
    stats_json = OUTDIR / "fan_synthesis_stats.json"
    stats_df.to_csv(stats_csv, index=False)
    stats_json.write_text(json.dumps(stats, indent=2))

    print(stats_csv)
    print(stats_json)
    print(ROUGH_MAG_PATH)
    print(ROUGH_SCALE_PATH)


if __name__ == "__main__":
    main()
