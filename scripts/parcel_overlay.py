from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd

from scripts.init_env import load_env
from scripts.study_config import (
    config_path,
    deliverable_path,
    step_path,
)
from scripts.study_utils import build_standard_map, ensure_crs

STREAMS_PATH = config_path("paths", "selected_streams")
PARCEL_BOUNDARY_PATH = config_path("paths", "parcel_boundary")
PARCEL_POLYGONS_PATH = config_path("paths", "parcel_polygons")
HAZARD_PATH = config_path("paths", "hazard_polygons")
LOCAL_AOI_PATH = config_path("paths", "local_aoi")
CONTEXT_AOI_PATH = config_path("paths", "context_aoi")
OUTDIR = step_path("parcel_overlay", "outdir")
MAP_PATH = deliverable_path("parcel_overlay_map")


@dataclass
class OverlayStats:
    layer_name: str
    total_length_m: float
    inside_parcel_m: float
    inside_hazard_m: float
    inside_parcel_and_hazard_m: float
    outside_parcel_m: float
    parcel_share: float
    hazard_share: float
    hazard_share_within_parcel: float
    segments: int
    segments_touching_parcel: int
    segments_touching_hazard: int
    segments_touching_both: int


def compute_overlay_metrics(
    streams: gpd.GeoDataFrame,
    parcel_boundary: gpd.GeoDataFrame,
    parcel_polygons: gpd.GeoDataFrame,
    hazard: gpd.GeoDataFrame,
    local_aoi: gpd.GeoDataFrame,
    context_aoi: gpd.GeoDataFrame,
    outdir: Path,
    clip_outputs: bool = True,
) -> tuple[pd.DataFrame, Path, Path, Path | None]:
    """Compute overlay metrics and write CSV/JSON to outdir. Returns (df, metrics_csv, metrics_json, clipped_gpkg)."""
    parcel_union = parcel_boundary.geometry.union_all()
    hazard_union = hazard.geometry.union_all()

    segs = streams[streams.geometry.notna()].copy()
    segs = segs[~segs.geometry.is_empty].copy()
    segs["length_m"] = segs.geometry.length
    segs["parcel_len_m"] = segs.geometry.intersection(parcel_union).length
    segs["hazard_len_m"] = segs.geometry.intersection(hazard_union).length
    segs["parcel_hazard_len_m"] = segs.geometry.intersection(parcel_union.intersection(hazard_union)).length
    segs["local_aoi_len_m"] = segs.geometry.intersection(local_aoi.geometry.union_all()).length
    segs["context_len_m"] = segs.geometry.intersection(context_aoi.geometry.union_all()).length
    segs["touches_parcel"] = segs["parcel_len_m"] > 0
    segs["touches_hazard"] = segs["hazard_len_m"] > 0
    segs["touches_both"] = segs["parcel_hazard_len_m"] > 0

    total_length = float(segs["length_m"].sum())
    parcel_length = float(segs["parcel_len_m"].sum())
    hazard_length = float(segs["hazard_len_m"].sum())
    parcel_hazard_length = float(segs["parcel_hazard_len_m"].sum())

    df = pd.DataFrame([
        asdict(OverlayStats(
            layer_name="selected_stream_network",
            total_length_m=total_length,
            inside_parcel_m=parcel_length,
            inside_hazard_m=hazard_length,
            inside_parcel_and_hazard_m=parcel_hazard_length,
            outside_parcel_m=total_length - parcel_length,
            parcel_share=(parcel_length / total_length) if total_length else 0.0,
            hazard_share=(hazard_length / total_length) if total_length else 0.0,
            hazard_share_within_parcel=(parcel_hazard_length / parcel_length) if parcel_length else 0.0,
            segments=int(len(segs)),
            segments_touching_parcel=int(segs["touches_parcel"].sum()),
            segments_touching_hazard=int(segs["touches_hazard"].sum()),
            segments_touching_both=int(segs["touches_both"].sum()),
        ))
    ])

    outdir.mkdir(parents=True, exist_ok=True)
    metrics_csv = outdir / "parcel_overlay_metrics.csv"
    metrics_json = outdir / "parcel_overlay_metrics.json"
    df.to_csv(metrics_csv, index=False)
    metrics_json.write_text(json.dumps(df.to_dict(orient="records"), indent=2))

    clipped_gpkg: Path | None = None
    if clip_outputs:
        inside = segs[segs["parcel_len_m"] > 0].copy()
        clipped_gpkg = outdir / "deanza_villas_2km_1m_dem_filled_streams_5000_in_parcel.gpkg"
        if clipped_gpkg.exists():
            clipped_gpkg.unlink()
        inside = inside.drop(columns=["touches_parcel", "touches_hazard", "touches_both"])
        inside.to_file(clipped_gpkg, driver="GPKG")

    return df, metrics_csv, metrics_json, clipped_gpkg


def main() -> None:
    load_env()

    # Read all vectors once; pass GeoDataFrames to all downstream functions.
    streams = ensure_crs(gpd.read_file(STREAMS_PATH))
    parcel_boundary = ensure_crs(gpd.read_file(PARCEL_BOUNDARY_PATH))
    parcel_polygons = ensure_crs(gpd.read_file(PARCEL_POLYGONS_PATH))
    hazard = ensure_crs(gpd.read_file(HAZARD_PATH))
    local_aoi = ensure_crs(gpd.read_file(LOCAL_AOI_PATH))
    context_aoi = ensure_crs(gpd.read_file(CONTEXT_AOI_PATH))

    df, metrics_csv, metrics_json, clipped_gpkg = compute_overlay_metrics(
        streams=streams,
        parcel_boundary=parcel_boundary,
        parcel_polygons=parcel_polygons,
        hazard=hazard,
        local_aoi=local_aoi,
        context_aoi=context_aoi,
        outdir=OUTDIR,
    )

    map_streams = clipped_gpkg if clipped_gpkg is not None and clipped_gpkg.exists() else STREAMS_PATH
    m = build_standard_map(
        center_gdf=parcel_boundary,
        zoom=16,
        satellite_basemap=True,
        hazard=hazard,
        context_aoi=context_aoi,
        local_aoi=local_aoi,
        parcel_polygons=parcel_polygons,
        parcel_boundary=parcel_boundary,
        streams=ensure_crs(gpd.read_file(map_streams)) if map_streams != STREAMS_PATH else streams,
    )
    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(MAP_PATH))

    print(metrics_csv)
    print(metrics_json)
    if clipped_gpkg is not None:
        print(clipped_gpkg)
    print(MAP_PATH)


if __name__ == "__main__":
    main()
