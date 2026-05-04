from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
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
) -> tuple[pd.DataFrame, Path, Path | None, int | None, int]:
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
    selected_threshold: int | None = None
    selected_gpkg: Path | None = None

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

        # D-infinity: vectorize manually via stream raster cells (D8 pointer
        # is invalid for D-infinity flow directions).  Use raster cell count
        # for stats rather than traced vector lengths.
        if flow_type == "dinf":
            import rasterio as _rio
            with _rio.open(stream_raster) as _sr:
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

    best_hazard = float(df["hazard_share"].max()) if not df.empty else 0.0
    top = df[df["hazard_share"] >= (0.95 * best_hazard)].copy() if best_hazard else df.copy()
    if not top.empty:
        top = top.sort_values(["total_length_m", "threshold_cells"], ascending=[True, True])
        selected_threshold = int(top.iloc[0]["threshold_cells"])
        selected_gpkg = outdir / f"{prefix_tag}{dem_path.stem}_streams_{selected_threshold}.gpkg"

    summary_csv = outdir / f"{prefix_tag}{dem_path.stem}_stream_threshold_sweep.csv"
    df.to_csv(summary_csv, index=False)

    summary_json = outdir / f"{prefix_tag}{dem_path.stem}_stream_threshold_sweep.json"
    safe_write_json(df.to_dict(orient="records"), summary_json)

    return df, summary_csv, selected_gpkg, selected_threshold, hazard_count


def main() -> None:
    # D8 stream extraction
    d8_df, d8_csv, d8_gpkg, d8_threshold, d8_hazard = derive_streams(
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
    dinf_df, dinf_csv, dinf_gpkg, dinf_threshold, dinf_hazard = derive_streams(
        dem_path=DEM_PATH,
        accum_path=DINF_ACCUM_PATH,
        pointer_path=POINTER_PATH,  # D8 pointer used for vectorization
        hazard_path=HAZARD_PATH,
        local_aoi_path=LOCAL_AOI_PATH,
        context_aoi_path=CONTEXT_AOI_PATH,
        outdir=OUTDIR,
        thresholds=DEFAULT_THRESHOLDS,
        flow_type="dinf",
        prefix_tag="dinf_",
    )

    print(f"d8_summary_csv: {d8_csv}")
    if d8_gpkg is not None:
        print(f"d8_selected_network: {d8_gpkg}")
    print(f"dinf_summary_csv: {dinf_csv}")
    if dinf_gpkg is not None:
        print(f"dinf_selected_network: {dinf_gpkg}")


if __name__ == "__main__":
    main()
