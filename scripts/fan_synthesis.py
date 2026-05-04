from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask
from scipy.ndimage import maximum_filter, minimum_filter
from whitebox.whitebox_tools import WhiteboxTools

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.init_env import load_env
from scripts.study_config import TARGET_CRS, deliverable_path, step_path
from scripts.study_utils import ensure_crs

DEFAULT_DEM = config_path("paths", "dem_filled")
DEFAULT_SLOPE = config_path("paths", "slope_degrees")
DEFAULT_STREAMS = config_path("paths", "selected_streams")
DEFAULT_PARCEL_BOUNDARY = config_path("paths", "parcel_boundary")
DEFAULT_PARCEL_POLYGONS = config_path("paths", "parcel_polygons")
DEFAULT_LOCAL_AOI = config_path("paths", "local_aoi")
DEFAULT_CONTEXT_AOI = config_path("paths", "context_aoi")
DEFAULT_HAZARD = config_path("paths", "hazard_polygons")
DEFAULT_OUTDIR = step_path("fan_synthesis", "outdir")
DEFAULT_REPORT = deliverable_path("fan_synthesis_report")
DEFAULT_MAP = deliverable_path("fan_synthesis_map")
DEFAULT_Rough_MAG = config_path("paths", "roughness_magnitude")
DEFAULT_Rough_SCALE = config_path("paths", "roughness_scale")


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


def _read_geom(path: Path) -> gpd.GeoDataFrame:
    return ensure_crs(gpd.read_file(path))


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


def _stream_stats(streams: gpd.GeoDataFrame, geom) -> tuple[float, int]:
    inside = streams[streams.intersects(geom)].copy()
    length = float(inside.geometry.intersection(geom).length.sum())
    return length, int(len(inside))


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
    stream_length_m, _ = _stream_stats(streams, geom)
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
    parcel_boundary_path: Path,
    parcel_polygons_path: Path,
    local_aoi_path: Path,
    context_aoi_path: Path,
    hazard_path: Path,
    streams_path: Path,
    rough_mag_path: Path,
    rough_scale_path: Path,
) -> None:
    parcel_overlay = pd.read_csv(parcel_overlay_csv)
    parcel_row = parcel_overlay.iloc[0]

    parcel_stats = stats_df[stats_df["area_name"] == "parcel"].iloc[0]
    local_stats = stats_df[stats_df["area_name"] == "local_aoi"].iloc[0]
    context_stats = stats_df[stats_df["area_name"] == "context_aoi"].iloc[0]

    lines: list[str] = []
    lines.append("# Fan Activity / Evidence Synthesis")
    lines.append("")
    lines.append("This step synthesizes the Borrego Springs fan-activity evidence from the official flood-protection documents and the 1 m De Anza Villas terrain derivatives.")
    lines.append("")
    lines.append("## Source-document signal")
    lines.append("")
    lines.append("- DRI 2015 active/inactive fan mapping: the Borrego Springs study area is dominated by active alluvial-fan landforms; the working summary used in this project is that about 90% of the 61 sq mi study area is geomorphically and hydraulically active.")
    lines.append("- Boyle / County guidance: flash floods move rapidly down desert canyons, smaller flows occupy existing washes until they are obstructed or aggrade, design-storm floods can sheet-flow across the fan and establish new washes, and all fan areas are subject to flooding unless properly protected.")
    lines.append("- County guidance also flags fan-terminus washes and local washes as flow-concentrating features that often need additional engineering analysis.")
    lines.append("")
    lines.append("## Terrain evidence from the 1 m DEM")
    lines.append("")
    lines.append("```csv")
    lines.append(stats_df.to_csv(index=False).rstrip())
    lines.append("```")
    lines.append("")
    lines.append("Interpretation:")
    lines.append(f"- The local 2 km AOI has a p95-p5 elevation relief of {local_stats['relief_p95_p5_m']:.1f} m, mean slope of {local_stats['slope_mean_deg']:.1f}°, and mean multiscale roughness of {local_stats['rough_mean_m']:.1f} m.")
    lines.append(f"- The De Anza Villas parcel boundary itself still carries {parcel_stats['relief_p95_p5_m']:.1f} m of p95-p5 relief, mean slope of {parcel_stats['slope_mean_deg']:.1f}°, and mean roughness of {parcel_stats['rough_mean_m']:.1f} m.")
    lines.append(f"- The broader fan context AOI remains rugged: p95-p5 relief {context_stats['relief_p95_p5_m']:.1f} m, mean slope {context_stats['slope_mean_deg']:.1f}°, mean roughness {context_stats['rough_mean_m']:.1f} m.")
    lines.append("")
    lines.append("## Wash / channel texture")
    lines.append("")
    lines.append(f"- Selected 5000-cell channel network length inside the parcel boundary: {parcel_row['inside_parcel_m']:.1f} m.")
    lines.append(f"- Parcel-length hazard overlap: {parcel_row['inside_parcel_and_hazard_m']:.1f} m ({parcel_row['hazard_share_within_parcel']:.1%} of parcel-crossing channel length).");
    lines.append(f"- Parcel stream density: {parcel_stats['stream_density_m_per_km2']:.1f} m/km², versus {context_stats['stream_density_m_per_km2']:.1f} m/km² across the 8 km fan context AOI.")
    lines.append(f"- The local 2 km AOI has {local_stats['stream_density_m_per_km2']:.1f} m/km², consistent with a concentrated drainage belt near the mountain-front/fan-transition area.")
    lines.append("")
    lines.append("## Fan-activity synthesis")
    lines.append("")
    lines.append("- Stage 1 — landform confirmation: Borrego Springs sits on coalescing alluvial fans fed by canyon systems; the parcel is on the fan surface, not an isolated benign upland.")
    lines.append("- Stage 2 — geomorphic activity: the DRI mapping and the dense, branching extracted wash network both support active-fan behavior rather than stable, fixed-drainage behavior.")
    lines.append("- Stage 3 — flood severity context: Boyle/County/FEMA context remains severe; the regulatory guidance treats the fan as flood-prone and acknowledges avulsion / new-wash formation risk.")
    lines.append("- Overall: the parcel sits within an active fan drainage fabric. The right reading is concentrated-flow exposure with channel mobility, not a one-time fixed-channel problem.")
    lines.append("")
    lines.append("## Outputs")
    lines.append("")
    lines.append(f"- Fan synthesis report: `{report_path.relative_to(ROOT)}`")
    lines.append(f"- Fan synthesis map: `{map_path.relative_to(ROOT)}`")
    lines.append(f"- Terrain stats CSV: `{stats_csv.relative_to(ROOT)}`")
    lines.append(f"- Terrain stats JSON: `{stats_json.relative_to(ROOT)}`")
    lines.append(f"- Roughness magnitude raster: `{rough_mag_path.relative_to(ROOT)}`")
    lines.append(f"- Roughness scale raster: `{rough_scale_path.relative_to(ROOT)}`")
    lines.append(f"- Parcel overlay metrics used here: `{parcel_overlay_csv.relative_to(ROOT)}`")
    lines.append(f"- Parcel boundary: `{parcel_boundary_path.relative_to(ROOT)}`")
    lines.append(f"- Parcel polygons: `{parcel_polygons_path.relative_to(ROOT)}`")
    lines.append(f"- Local AOI: `{local_aoi_path.relative_to(ROOT)}`")
    lines.append(f"- Context AOI: `{context_aoi_path.relative_to(ROOT)}`")
    lines.append(f"- Hazard polygons: `{hazard_path.relative_to(ROOT)}`")
    lines.append(f"- Selected channel network: `{streams_path.relative_to(ROOT)}`")
    lines.append("")
    lines.append("## Caveat")
    lines.append("")
    lines.append("These are evidence-synthesis outputs from public documents and terrain analysis, not a stamped engineering flood report or FEMA map revision.")

    report_path.write_text("\n".join(lines) + "\n")


def write_map(
    map_path: Path,
    streams_path: Path,
    parcel_boundary_path: Path,
    parcel_polygons_path: Path,
    local_aoi_path: Path,
    context_aoi_path: Path,
    hazard_path: Path,
) -> None:
    streams = ensure_crs(gpd.read_file(streams_path)).to_crs(4326)
    parcel_boundary = ensure_crs(gpd.read_file(parcel_boundary_path)).to_crs(4326)
    parcel_polygons = ensure_crs(gpd.read_file(parcel_polygons_path)).to_crs(4326)
    local_aoi = ensure_crs(gpd.read_file(local_aoi_path)).to_crs(4326)
    context_aoi = ensure_crs(gpd.read_file(context_aoi_path)).to_crs(4326)
    hazard = ensure_crs(gpd.read_file(hazard_path)).to_crs(4326)

    center = parcel_boundary.geometry.iloc[0].centroid
    m = folium.Map(location=[center.y, center.x], zoom_start=15, tiles=None)
    folium.TileLayer("Esri.WorldImagery", name="Satellite imagery", attr="Esri").add_to(m)
    folium.TileLayer("CartoDB positron", name="Light basemap", attr="CartoDB").add_to(m)

    folium.GeoJson(
        hazard,
        name="Mapped flood hazard polygons",
        style_function=lambda _feature: {"fillColor": "#e34a33", "color": "#b30000", "weight": 1, "fillOpacity": 0.18},
        tooltip=folium.GeoJsonTooltip(fields=["flood_plai"], aliases=["Hazard class"]),
    ).add_to(m)

    folium.GeoJson(
        context_aoi,
        name="8 km fan context AOI",
        style_function=lambda _feature: {"fill": False, "color": "#636363", "weight": 2, "dashArray": "4 4"},
    ).add_to(m)

    folium.GeoJson(
        local_aoi,
        name="2 km local AOI",
        style_function=lambda _feature: {"fill": False, "color": "#969696", "weight": 2, "dashArray": "2 4"},
    ).add_to(m)

    folium.GeoJson(
        parcel_polygons,
        name="De Anza Villas parcel polygons",
        style_function=lambda _feature: {"fillColor": "#9ecae1", "color": "#3182bd", "weight": 1, "fillOpacity": 0.12},
        tooltip=folium.GeoJsonTooltip(fields=["apn", "situs_address", "subname"], aliases=["APN", "Address", "Subname"]),
    ).add_to(m)

    folium.GeoJson(
        parcel_boundary,
        name="Dissolved parcel boundary",
        style_function=lambda _feature: {"fill": False, "color": "#000000", "weight": 3},
        tooltip=folium.GeoJsonTooltip(fields=["name", "parcel_count"], aliases=["Name", "Parcels"]),
    ).add_to(m)

    folium.GeoJson(
        streams,
        name="Selected channel network",
        style_function=lambda _feature: {"color": "#2b8cbe", "weight": 2, "opacity": 0.85},
    ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    map_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(map_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Complete fan-activity synthesis for De Anza Villas.")
    parser.add_argument("--dem", type=Path, default=DEFAULT_DEM)
    parser.add_argument("--slope", type=Path, default=DEFAULT_SLOPE)
    parser.add_argument("--streams", type=Path, default=DEFAULT_STREAMS)
    parser.add_argument("--parcel-boundary", type=Path, default=DEFAULT_PARCEL_BOUNDARY)
    parser.add_argument("--parcel-polygons", type=Path, default=DEFAULT_PARCEL_POLYGONS)
    parser.add_argument("--local-aoi", type=Path, default=DEFAULT_LOCAL_AOI)
    parser.add_argument("--context-aoi", type=Path, default=DEFAULT_CONTEXT_AOI)
    parser.add_argument("--hazard", type=Path, default=DEFAULT_HAZARD)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--map-path", type=Path, default=DEFAULT_MAP)
    args = parser.parse_args()

    load_env()

    rough_mag = DEFAULT_Rough_MAG
    rough_scale = DEFAULT_Rough_SCALE
    ensure_roughness(args.dem, rough_mag, rough_scale)

    streams = ensure_crs(gpd.read_file(args.streams))
    parcel = ensure_crs(gpd.read_file(args.parcel_boundary)).geometry.iloc[0]
    local_aoi = ensure_crs(gpd.read_file(args.local_aoi)).geometry.iloc[0]
    context_aoi = ensure_crs(gpd.read_file(args.context_aoi)).geometry.iloc[0]

    stats = [
        asdict(build_area_stats("parcel", parcel, args.dem, args.slope, rough_mag, streams)),
        asdict(build_area_stats("local_aoi", local_aoi, args.dem, args.slope, rough_mag, streams)),
        asdict(build_area_stats("context_aoi", context_aoi, args.dem, args.slope, rough_mag, streams)),
    ]
    stats_df = pd.DataFrame(stats)

    outdir = args.outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    stats_csv = outdir / "fan_synthesis_stats.csv"
    stats_json = outdir / "fan_synthesis_stats.json"
    stats_df.to_csv(stats_csv, index=False)
    stats_json.write_text(json.dumps(stats, indent=2))

    report_path = args.report.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_report(
        report_path=report_path,
        stats_df=stats_df,
        stats_csv=stats_csv,
        stats_json=stats_json,
        parcel_overlay_csv=step_path("parcel_overlay", "metrics_csv"),
        parcel_boundary_path=args.parcel_boundary,
        parcel_polygons_path=args.parcel_polygons,
        local_aoi_path=args.local_aoi,
        context_aoi_path=args.context_aoi,
        hazard_path=args.hazard,
        streams_path=args.streams,
        rough_mag_path=rough_mag,
        rough_scale_path=rough_scale,
    )

    write_map(
        map_path=args.map_path.resolve(),
        streams_path=args.streams,
        parcel_boundary_path=args.parcel_boundary,
        parcel_polygons_path=args.parcel_polygons,
        local_aoi_path=args.local_aoi,
        context_aoi_path=args.context_aoi,
        hazard_path=args.hazard,
    )

    print(report_path)
    print(stats_csv)
    print(stats_json)
    print(rough_mag)
    print(rough_scale)
    print(args.map_path.resolve())


if __name__ == "__main__":
    main()
