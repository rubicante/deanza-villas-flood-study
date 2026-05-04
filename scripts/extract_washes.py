from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from whitebox.whitebox_tools import WhiteboxTools

from scripts.init_env import load_env
from scripts.study_config import (
    DEFAULT_THRESHOLDS,
    TARGET_CRS,
    config_path,
    step_path,
)
from scripts.study_utils import safe_write_json

DEM_PATH = config_path("paths", "dem_filled")
D8_ACCUM_PATH = config_path("paths", "d8_flow_accum")
DINF_ACCUM_PATH = config_path("paths", "dinf_flow_accum")
POINTER_PATH = config_path("paths", "d8_pointer")
HAZARD_PATH = config_path("paths", "hazard_polygons")
LOCAL_AOI_PATH = config_path("paths", "local_aoi")
CONTEXT_AOI_PATH = config_path("paths", "context_aoi")
OUTDIR = step_path("wash_extraction", "outdir")


@dataclass
class ThresholdStats:
    threshold_cells: int
    segments: int
    total_length_m: float
    hazard_length_m: float
    hazard_share: float
    local_aoi_share: float
    context_share: float
    mean_segment_length_m: float
    max_segment_length_m: float
    segments_touching_hazard: int
    flow_type: str = "d8"


@dataclass
class ZoneBetweenStats:
    low_threshold: int
    high_threshold: int
    between_cells: int
    between_cells_local_aoi: int
    between_cells_parcel: int
    flow_type: str


def _clean_shapefile_outputs(path: Path) -> None:
    for suffix in [".shp", ".shx", ".dbf", ".prj", ".cpg", ".qpj"]:
        candidate = path.with_suffix(suffix)
        if candidate.exists():
            candidate.unlink()


def derive_streams(
    dem_path: Path,
    accum_path: Path,
    pointer_path: Path,
    hazard_path: Path,
    local_aoi_path: Path,
    context_aoi_path: Path,
    outdir: Path,
    thresholds: list[int],
    flow_type: str = "d8",
    prefix_tag: str = "",
) -> tuple[pd.DataFrame, Path, int]:
    """Extract streams at all thresholds. Returns (df, summary_csv, hazard_count).

    All thresholds are kept as a full ensemble — no single "best" is selected.
    The full sweep CSV and all threshold GPKGs/rasters are the canonical outputs.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    dem_path = dem_path.resolve()
    accum_path = accum_path.resolve()
    pointer_path = pointer_path.resolve()
    hazard_path = hazard_path.resolve()
    local_aoi_path = local_aoi_path.resolve()
    context_aoi_path = context_aoi_path.resolve()
    outdir = outdir.resolve()

    load_env()

    wbt = WhiteboxTools()
    wbt.set_working_dir(str(outdir))
    wbt.set_verbose_mode(False)

    hazard = gpd.read_file(hazard_path).to_crs(TARGET_CRS)
    hazard_union = hazard.geometry.union_all()
    hazard_count = int(len(hazard))
    local_aoi = gpd.read_file(local_aoi_path).to_crs(TARGET_CRS).geometry.iloc[0]
    context_aoi = gpd.read_file(context_aoi_path).to_crs(TARGET_CRS).geometry.iloc[0]

    rows: list[dict[str, object]] = []

    for threshold in thresholds:
        stream_raster = outdir / f"{prefix_tag}{dem_path.stem}_streams_{threshold}.tif"
        stream_shape = outdir / f"{prefix_tag}{dem_path.stem}_streams_{threshold}.shp"
        stream_gpkg = outdir / f"{prefix_tag}{dem_path.stem}_streams_{threshold}.gpkg"

        _clean_shapefile_outputs(stream_shape)
        if stream_gpkg.exists():
            stream_gpkg.unlink()
        if stream_raster.exists():
            stream_raster.unlink()

        wbt.extract_streams(str(accum_path), str(stream_raster), threshold, zero_background=True)

        # D-infinity: raster cell counts only (no valid D8-pointer vectorization)
        if flow_type == "dinf":
            with rasterio.open(stream_raster) as _sr:
                _sdata = _sr.read(1)
                stream_cells = int((_sdata > 0).sum())
            rows.append({
                "threshold_cells": threshold,
                "segments": 0, "total_length_m": float(stream_cells),
                "hazard_length_m": 0.0, "hazard_share": 0.0,
                "local_aoi_share": 0.0, "context_share": 0.0,
                "mean_segment_length_m": 0.0, "max_segment_length_m": 0.0,
                "segments_touching_hazard": 0, "flow_type": flow_type,
            })
            continue

        wbt.raster_streams_to_vector(str(stream_raster), str(pointer_path), str(stream_shape))

        gdf = gpd.read_file(stream_shape).set_crs(TARGET_CRS, allow_override=True)
        gdf = gdf[gdf.geometry.notna()].copy()
        gdf = gdf[~gdf.geometry.is_empty].copy()
        gdf["length_m"] = gdf.geometry.length
        gdf["hazard_len_m"] = gdf.geometry.intersection(hazard_union).length
        gdf["local_aoi_len_m"] = gdf.geometry.intersection(local_aoi).length
        gdf["context_len_m"] = gdf.geometry.intersection(context_aoi).length
        gdf["touches_hazard"] = gdf["hazard_len_m"] > 0

        total_length = float(gdf["length_m"].sum())
        hazard_length = float(gdf["hazard_len_m"].sum())
        local_length = float(gdf["local_aoi_len_m"].sum())
        context_length = float(gdf["context_len_m"].sum())
        stats = ThresholdStats(
            threshold_cells=threshold,
            segments=int(len(gdf)),
            total_length_m=total_length,
            hazard_length_m=hazard_length,
            hazard_share=(hazard_length / total_length) if total_length else 0.0,
            local_aoi_share=(local_length / total_length) if total_length else 0.0,
            context_share=(context_length / total_length) if total_length else 0.0,
            mean_segment_length_m=(total_length / len(gdf)) if len(gdf) else 0.0,
            max_segment_length_m=float(gdf["length_m"].max()) if len(gdf) else 0.0,
            segments_touching_hazard=int(gdf["touches_hazard"].sum()),
            flow_type=flow_type,
        )
        rows.append(asdict(stats))

        gdf.drop(columns=["touches_hazard"], inplace=True)
        gdf.to_file(stream_gpkg, driver="GPKG")

    df = pd.DataFrame(rows).sort_values("threshold_cells").reset_index(drop=True)

    summary_csv = outdir / f"{prefix_tag}{dem_path.stem}_stream_threshold_sweep.csv"
    df.to_csv(summary_csv, index=False)

    summary_json = outdir / f"{prefix_tag}{dem_path.stem}_stream_threshold_sweep.json"
    safe_write_json(df.to_dict(orient="records"), summary_json)

    return df, summary_csv, hazard_count


def compute_between_threshold_zones(
    outdir: Path,
    thresholds: list[int],
    dem_stem: str,
    local_aoi_path: Path,
    parcel_path: Path | None = None,
) -> list[ZoneBetweenStats]:
    """Compare adjacent threshold stream rasters. Cells active at the lower
    threshold but NOT at the higher threshold are potential avulsion paths."""
    sorted_t = sorted(thresholds)
    results: list[ZoneBetweenStats] = []

    local_aoi = gpd.read_file(local_aoi_path).to_crs(TARGET_CRS)
    local_geom = local_aoi.geometry.iloc[0]

    parcel_geom = None
    if parcel_path and parcel_path.exists():
        parcel = gpd.read_file(parcel_path).to_crs(TARGET_CRS)
        parcel_geom = parcel.geometry.iloc[0]

    for i in range(len(sorted_t) - 1):
        t_low, t_high = sorted_t[i], sorted_t[i + 1]
        low_path = outdir / f"{dem_stem}_streams_{t_low}.tif"
        high_path = outdir / f"{dem_stem}_streams_{t_high}.tif"
        if not low_path.exists() or not high_path.exists():
            continue

        with rasterio.open(low_path) as low_src:
            low_data = low_src.read(1)
            transform = low_src.transform
            with rasterio.open(high_path) as high_src:
                high_data = high_src.read(1)

        # Binary: 1 = stream, 0 = no stream (zero_background was used)
        low_binary = (low_data > 0).astype(np.uint8)
        high_binary = (high_data > 0).astype(np.uint8)
        between = (low_binary == 1) & (high_binary == 0)
        between_cells = int(between.sum())

        # Count between-zone cells within local AOI and parcel
        between_local = 0
        between_parcel = 0
        if between_cells > 0:
            from rasterio.features import geometry_mask
            local_mask_arr = geometry_mask(
                [local_geom], out_shape=between.shape,
                transform=transform, invert=True,
            )
            between_local = int((between & local_mask_arr).sum())
            if parcel_geom is not None:
                parcel_mask_arr = geometry_mask(
                    [parcel_geom], out_shape=between.shape,
                    transform=transform, invert=True,
                )
                between_parcel = int((between & parcel_mask_arr).sum())

        results.append(ZoneBetweenStats(
            low_threshold=t_low,
            high_threshold=t_high,
            between_cells=between_cells,
            between_cells_local_aoi=between_local,
            between_cells_parcel=between_parcel,
            flow_type="d8",
        ))

    return results


def main() -> None:
    # D8 stream extraction — full ensemble, all thresholds
    d8_df, d8_csv, d8_hazard = derive_streams(
        dem_path=DEM_PATH,
        accum_path=D8_ACCUM_PATH,
        pointer_path=POINTER_PATH,
        hazard_path=HAZARD_PATH,
        local_aoi_path=LOCAL_AOI_PATH,
        context_aoi_path=CONTEXT_AOI_PATH,
        outdir=OUTDIR,
        thresholds=DEFAULT_THRESHOLDS,
        flow_type="d8",
        prefix_tag="",
    )

    # D-infinity stream extraction
    dinf_df, dinf_csv, dinf_hazard = derive_streams(
        dem_path=DEM_PATH,
        accum_path=DINF_ACCUM_PATH,
        pointer_path=POINTER_PATH,
        hazard_path=HAZARD_PATH,
        local_aoi_path=LOCAL_AOI_PATH,
        context_aoi_path=CONTEXT_AOI_PATH,
        outdir=OUTDIR,
        thresholds=DEFAULT_THRESHOLDS,
        flow_type="dinf",
        prefix_tag="dinf_",
    )

    # Between-threshold zone analysis (D8 only — meaningful vectorization)
    parcel_path = config_path("paths", "parcel_boundary")
    between_zones = compute_between_threshold_zones(
        outdir=OUTDIR,
        thresholds=DEFAULT_THRESHOLDS,
        dem_stem=DEM_PATH.stem,
        local_aoi_path=LOCAL_AOI_PATH,
        parcel_path=parcel_path,
    )

    # Save between-threshold zone summary
    if between_zones:
        between_df = pd.DataFrame([asdict(z) for z in between_zones])
        between_csv = OUTDIR / f"{DEM_PATH.stem}_between_threshold_zones.csv"
        between_json = OUTDIR / f"{DEM_PATH.stem}_between_threshold_zones.json"
        between_df.to_csv(between_csv, index=False)
        safe_write_json(between_df.to_dict(orient="records"), between_json)
        print(f"between_zones_csv: {between_csv}")

    print(f"d8_summary_csv: {d8_csv}")
    print(f"dinf_summary_csv: {dinf_csv}")


if __name__ == "__main__":
    main()
