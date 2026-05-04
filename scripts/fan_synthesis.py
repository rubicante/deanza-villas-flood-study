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
    ROOT,
    config_path,
    deliverable_path,
    step_path,
)
from scripts.study_utils import build_standard_map, ensure_crs

DEM_PATH = config_path("paths", "dem_filled")
SLOPE_PATH = config_path("paths", "slope_degrees")
STREAMS_PATH = config_path("paths", "selected_streams")
PARCEL_BOUNDARY_PATH = config_path("paths", "parcel_boundary")
PARCEL_POLYGONS_PATH = config_path("paths", "parcel_polygons")
LOCAL_AOI_PATH = config_path("paths", "local_aoi")
CONTEXT_AOI_PATH = config_path("paths", "context_aoi")
HAZARD_PATH = config_path("paths", "hazard_polygons")
ROUGH_MAG_PATH = config_path("paths", "roughness_magnitude")
ROUGH_SCALE_PATH = config_path("paths", "roughness_scale")
OUTDIR = step_path("fan_synthesis", "outdir")
REPORT_PATH = deliverable_path("fan_synthesis_report")
MAP_PATH = deliverable_path("fan_synthesis_map")


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


def write_report(
    report_path: Path,
    stats_df: pd.DataFrame,
    stats_csv: Path,
    stats_json: Path,
    parcel_overlay_csv: Path,
) -> None:
    parcel_overlay = pd.read_csv(parcel_overlay_csv)
    parcel_row = parcel_overlay.iloc[0]

    parcel_stats = stats_df[stats_df["area_name"] == "parcel"].iloc[0]
    local_stats = stats_df[stats_df["area_name"] == "local_aoi"].iloc[0]
    context_stats = stats_df[stats_df["area_name"] == "context_aoi"].iloc[0]

    report = f"""\
# Fan Activity / Evidence Synthesis

This step synthesizes the Borrego Springs fan-activity evidence from the official flood-protection documents and the 1 m De Anza Villas terrain derivatives.

## Source-document signal

- DRI 2015 active/inactive fan mapping: the Borrego Springs study area is dominated by active alluvial-fan landforms; the working summary used in this project is that about 90% of the 61 sq mi study area is geomorphically and hydraulically active.
- Boyle / County guidance: flash floods move rapidly down desert canyons, smaller flows occupy existing washes until they are obstructed or aggrade, design-storm floods can sheet-flow across the fan and establish new washes, and all fan areas are subject to flooding unless properly protected.
- County guidance also flags fan-terminus washes and local washes as flow-concentrating features that often need additional engineering analysis.

## Terrain evidence from the 1 m DEM

```csv
{stats_df.to_csv(index=False).rstrip()}
```

Interpretation:
- The local 2 km AOI has a p95-p5 elevation relief of {local_stats['relief_p95_p5_m']:.1f} m, mean slope of {local_stats['slope_mean_deg']:.1f}°, and mean multiscale roughness of {local_stats['rough_mean_m']:.1f} m.
- The De Anza Villas parcel boundary itself still carries {parcel_stats['relief_p95_p5_m']:.1f} m of p95-p5 relief, mean slope of {parcel_stats['slope_mean_deg']:.1f}°, and mean roughness of {parcel_stats['rough_mean_m']:.1f} m.
- The broader fan context AOI remains rugged: p95-p5 relief {context_stats['relief_p95_p5_m']:.1f} m, mean slope {context_stats['slope_mean_deg']:.1f}°, mean roughness {context_stats['rough_mean_m']:.1f} m.

## Wash / channel texture

- Selected 5000-cell channel network length inside the parcel boundary: {parcel_row['inside_parcel_m']:.1f} m.
- Parcel-length hazard overlap: {parcel_row['inside_parcel_and_hazard_m']:.1f} m ({parcel_row['hazard_share_within_parcel']:.1%} of parcel-crossing channel length).
- Parcel stream density: {parcel_stats['stream_density_m_per_km2']:.1f} m/km², versus {context_stats['stream_density_m_per_km2']:.1f} m/km² across the 8 km fan context AOI.
- The local 2 km AOI has {local_stats['stream_density_m_per_km2']:.1f} m/km², consistent with a concentrated drainage belt near the mountain-front/fan-transition area.

## Fan-activity synthesis

- Stage 1 — landform confirmation: Borrego Springs sits on coalescing alluvial fans fed by canyon systems; the parcel is on the fan surface, not an isolated benign upland.
- Stage 2 — geomorphic activity: the DRI mapping and the dense, branching extracted wash network both support active-fan behavior rather than stable, fixed-drainage behavior.
- Stage 3 — flood severity context: Boyle/County/FEMA context remains severe; the regulatory guidance treats the fan as flood-prone and acknowledges avulsion / new-wash formation risk.
- Overall: the parcel sits within an active fan drainage fabric. The right reading is concentrated-flow exposure with channel mobility, not a one-time fixed-channel problem.

## Outputs

- Fan synthesis report: `{report_path.relative_to(ROOT)}`
- Fan synthesis map: `{MAP_PATH.relative_to(ROOT)}`
- Terrain stats CSV: `{stats_csv.relative_to(ROOT)}`
- Terrain stats JSON: `{stats_json.relative_to(ROOT)}`
- Roughness magnitude raster: `{ROUGH_MAG_PATH.relative_to(ROOT)}`
- Roughness scale raster: `{ROUGH_SCALE_PATH.relative_to(ROOT)}`
- Parcel overlay metrics used here: `{parcel_overlay_csv.relative_to(ROOT)}`
- Parcel boundary: `{PARCEL_BOUNDARY_PATH.relative_to(ROOT)}`
- Parcel polygons: `{PARCEL_POLYGONS_PATH.relative_to(ROOT)}`
- Local AOI: `{LOCAL_AOI_PATH.relative_to(ROOT)}`
- Context AOI: `{CONTEXT_AOI_PATH.relative_to(ROOT)}`
- Hazard polygons: `{HAZARD_PATH.relative_to(ROOT)}`
- Selected channel network: `{STREAMS_PATH.relative_to(ROOT)}`

## Caveat

These are evidence-synthesis outputs from public documents and terrain analysis, not a stamped engineering flood report or FEMA map revision.
"""

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")


def main() -> None:
    load_env()

    ensure_roughness(DEM_PATH, ROUGH_MAG_PATH, ROUGH_SCALE_PATH)

    # Read vectors once; pass GeoDataFrames to all downstream functions.
    streams = ensure_crs(gpd.read_file(STREAMS_PATH))
    parcel_boundary = ensure_crs(gpd.read_file(PARCEL_BOUNDARY_PATH))
    parcel_polygons = ensure_crs(gpd.read_file(PARCEL_POLYGONS_PATH))
    local_aoi = ensure_crs(gpd.read_file(LOCAL_AOI_PATH))
    context_aoi = ensure_crs(gpd.read_file(CONTEXT_AOI_PATH))
    hazard = ensure_crs(gpd.read_file(HAZARD_PATH))

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

    write_report(
        report_path=REPORT_PATH,
        stats_df=stats_df,
        stats_csv=stats_csv,
        stats_json=stats_json,
        parcel_overlay_csv=step_path("parcel_overlay", "metrics_csv"),
    )

    m = build_standard_map(
        center_gdf=parcel_boundary,
        zoom=15,
        satellite_basemap=True,
        hazard=hazard,
        context_aoi=context_aoi,
        local_aoi=local_aoi,
        parcel_polygons=parcel_polygons,
        parcel_boundary=parcel_boundary,
        streams=streams,
    )
    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(MAP_PATH))

    print(REPORT_PATH)
    print(stats_csv)
    print(stats_json)
    print(ROUGH_MAG_PATH)
    print(ROUGH_SCALE_PATH)
    print(MAP_PATH)


if __name__ == "__main__":
    main()
