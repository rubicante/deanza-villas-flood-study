from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
import sys

import geopandas as gpd
import pandas as pd
import folium

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.init_env import load_env

TARGET_CRS = "EPSG:5070"

DEFAULT_STREAMS = ROOT / "data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg"
DEFAULT_PARCEL_BOUNDARY = ROOT / "data/vectors/deanza_villas_complex_boundary.geojson"
DEFAULT_PARCEL_POLYGONS = ROOT / "data/vectors/deanza_villas_parcel_polygons.geojson"
DEFAULT_HAZARD = ROOT / "data/raw/fema/oes_know_your_hazards_flooding_borrego.geojson"
DEFAULT_LOCAL_AOI = ROOT / "data/vectors/deanza_villas_2km_aoi.geojson"
DEFAULT_CONTEXT_AOI = ROOT / "data/vectors/borrego_valley_context_8km_aoi.geojson"
DEFAULT_OUTDIR = ROOT / "data/processed/terrain/deanza_villas_2km_1m/parcels"
DEFAULT_REPORT_DIR = ROOT / "outputs/reports"
DEFAULT_MAP_PATH = ROOT / "outputs/maps/phase3_parcel_context.html"


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


def _ensure_crs(gdf: gpd.GeoDataFrame, crs: str = TARGET_CRS) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    return gdf.to_crs(crs)


def _style_boundary(_feature):
    return {"fill": False, "color": "#000000", "weight": 3}


def _style_parcels(_feature):
    return {"fillColor": "#6baed6", "color": "#2171b5", "weight": 1, "fillOpacity": 0.12}


def _style_hazard(feature):
    cls = feature["properties"].get("flood_plai")
    if cls == "FW100":
        return {"fillColor": "#d7301f", "color": "#a50f15", "weight": 1, "fillOpacity": 0.30}
    return {"fillColor": "#fc8d59", "color": "#d7301f", "weight": 1, "fillOpacity": 0.16}


def _style_streams(_feature):
    return {"color": "#2c7fb8", "weight": 2, "opacity": 0.85}


def _style_streams_inside(_feature):
    return {"color": "#006d2c", "weight": 3, "opacity": 0.95}


def compute_overlay_metrics(
    streams_path: Path,
    parcel_boundary_path: Path,
    parcel_polygons_path: Path,
    hazard_path: Path,
    local_aoi_path: Path,
    context_aoi_path: Path,
    outdir: Path,
    clip_outputs: bool = True,
) -> tuple[pd.DataFrame, Path, Path, Path | None]:
    load_env()

    streams = _ensure_crs(gpd.read_file(streams_path))
    parcel_boundary = _ensure_crs(gpd.read_file(parcel_boundary_path))
    parcel_polygons = _ensure_crs(gpd.read_file(parcel_polygons_path))
    hazard = _ensure_crs(gpd.read_file(hazard_path))
    local_aoi = _ensure_crs(gpd.read_file(local_aoi_path))
    context_aoi = _ensure_crs(gpd.read_file(context_aoi_path))

    parcel_union = parcel_boundary.geometry.union_all()
    hazard_union = hazard.geometry.union_all()
    local_union = local_aoi.geometry.union_all()
    context_union = context_aoi.geometry.union_all()

    streams = streams[streams.geometry.notna()].copy()
    streams = streams[~streams.geometry.is_empty].copy()
    streams["length_m"] = streams.geometry.length
    streams["parcel_len_m"] = streams.geometry.intersection(parcel_union).length
    streams["hazard_len_m"] = streams.geometry.intersection(hazard_union).length
    streams["parcel_hazard_len_m"] = streams.geometry.intersection(parcel_union.intersection(hazard_union)).length
    streams["local_aoi_len_m"] = streams.geometry.intersection(local_union).length
    streams["context_len_m"] = streams.geometry.intersection(context_union).length
    streams["touches_parcel"] = streams["parcel_len_m"] > 0
    streams["touches_hazard"] = streams["hazard_len_m"] > 0
    streams["touches_both"] = streams["parcel_hazard_len_m"] > 0

    total_length = float(streams["length_m"].sum())
    parcel_length = float(streams["parcel_len_m"].sum())
    hazard_length = float(streams["hazard_len_m"].sum())
    parcel_hazard_length = float(streams["parcel_hazard_len_m"].sum())
    outside_parcel_length = total_length - parcel_length

    parcel_layer = pd.DataFrame(
        [
            asdict(
                OverlayStats(
                    layer_name="selected_stream_network",
                    total_length_m=total_length,
                    inside_parcel_m=parcel_length,
                    inside_hazard_m=hazard_length,
                    inside_parcel_and_hazard_m=parcel_hazard_length,
                    outside_parcel_m=outside_parcel_length,
                    parcel_share=(parcel_length / total_length) if total_length else 0.0,
                    hazard_share=(hazard_length / total_length) if total_length else 0.0,
                    hazard_share_within_parcel=(parcel_hazard_length / parcel_length) if parcel_length else 0.0,
                    segments=int(len(streams)),
                    segments_touching_parcel=int(streams["touches_parcel"].sum()),
                    segments_touching_hazard=int(streams["touches_hazard"].sum()),
                    segments_touching_both=int(streams["touches_both"].sum()),
                )
            )
        ]
    )

    outdir.mkdir(parents=True, exist_ok=True)
    metrics_csv = outdir / "phase3_parcel_overlay_metrics.csv"
    metrics_json = outdir / "phase3_parcel_overlay_metrics.json"
    parcel_layer.to_csv(metrics_csv, index=False)
    metrics_json.write_text(json.dumps(parcel_layer.to_dict(orient="records"), indent=2))

    clipped_gpkg: Path | None = None
    if clip_outputs:
        inside = streams[streams["parcel_len_m"] > 0].copy()
        clipped_gpkg = outdir / "deanza_villas_2km_1m_dem_filled_streams_5000_in_parcel.gpkg"
        if clipped_gpkg.exists():
            clipped_gpkg.unlink()
        inside = inside.drop(columns=["touches_parcel", "touches_hazard", "touches_both"])  # keep clean output
        inside.to_file(clipped_gpkg, driver="GPKG")

    return parcel_layer, metrics_csv, metrics_json, clipped_gpkg


def write_report(
    df: pd.DataFrame,
    report_path: Path,
    streams_path: Path,
    parcel_boundary_path: Path,
    parcel_polygons_path: Path,
    hazard_path: Path,
    local_aoi_path: Path,
    context_aoi_path: Path,
    metrics_csv: Path,
    metrics_json: Path,
    clipped_gpkg: Path | None,
) -> None:
    parcel_boundary = _ensure_crs(gpd.read_file(parcel_boundary_path))
    parcel_polygons = _ensure_crs(gpd.read_file(parcel_polygons_path))
    hazard = _ensure_crs(gpd.read_file(hazard_path))
    local_aoi = _ensure_crs(gpd.read_file(local_aoi_path))
    context_aoi = _ensure_crs(gpd.read_file(context_aoi_path))

    row = df.iloc[0]
    lines: list[str] = []
    lines.append("# Phase 3 Parcel Overlay")
    lines.append("")
    lines.append("This step wired the authoritative De Anza Villas parcel geometry into the selected 5000-cell channel network and re-ran the overlay metrics against the hazard and fan-context layers.")
    lines.append("")
    lines.append("## Inputs used")
    lines.append(f"- Selected stream network: `{streams_path.relative_to(ROOT)}`")
    lines.append(f"- Parcel boundary: `{parcel_boundary_path.relative_to(ROOT)}`")
    lines.append(f"- Parcel polygons: `{parcel_polygons_path.relative_to(ROOT)}` ({len(parcel_polygons)} features)")
    lines.append(f"- Hazard polygons: `{hazard_path.relative_to(ROOT)}` ({len(hazard)} features)")
    lines.append(f"- Local AOI: `{local_aoi_path.relative_to(ROOT)}`")
    lines.append(f"- Context AOI: `{context_aoi_path.relative_to(ROOT)}`")
    lines.append("")
    lines.append("## Parcel-aware overlay metrics")
    lines.append("")
    lines.append("```csv")
    lines.append(df.to_csv(index=False).rstrip())
    lines.append("```")
    lines.append("")
    lines.append("Key readout:")
    lines.append(f"- network length inside parcel boundary: {row['inside_parcel_m']:.1f} m ({row['parcel_share']:.1%})")
    lines.append(f"- network length inside mapped hazard polygons: {row['inside_hazard_m']:.1f} m ({row['hazard_share']:.1%})")
    lines.append(f"- network length inside both parcel boundary and hazard polygons: {row['inside_parcel_and_hazard_m']:.1f} m")
    lines.append(f"- hazard share within parcel boundary: {row['hazard_share_within_parcel']:.1%}")
    lines.append(f"- segments touching parcel boundary: {int(row['segments_touching_parcel'])} of {int(row['segments'])}")
    lines.append(f"- segments touching hazard polygons: {int(row['segments_touching_hazard'])} of {int(row['segments'])}")
    lines.append(f"- segments touching both parcel and hazard: {int(row['segments_touching_both'])} of {int(row['segments'])}")
    lines.append("")
    if clipped_gpkg is not None:
        lines.append(f"Clipped parcel-only stream layer: `{clipped_gpkg.relative_to(ROOT)}`")
        lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- The authoritative boundary confirms how much of the selected drainage network actually crosses or sits within the De Anza Villas parcel complex.")
    lines.append("- Comparing the network to the dissolved parcel boundary avoids using a hand-drawn approximation for parcel-scale risk context.")
    lines.append("- The hazard overlap remains substantial after parcel-aware clipping, so the parcel context does not eliminate the channel/wash signal; it localizes it.")
    lines.append("- The parcel polygons are preserved as a separate layer for later per-APN interrogation, while the dissolved boundary is the canonical single-file parcel geometry.")
    lines.append("")
    lines.append("## Context caveat")
    lines.append("")
    lines.append("These are terrain-derived and parcel-overlay context metrics, not a licensed engineering flood determination or FEMA map revision.")
    lines.append("")
    lines.append("## Outputs")
    lines.append("")
    lines.append(f"- Metrics CSV: `{metrics_csv.relative_to(ROOT)}`")
    lines.append(f"- Metrics JSON: `{metrics_json.relative_to(ROOT)}`")
    if clipped_gpkg is not None:
        lines.append(f"- Parcel-only stream GPKG: `{clipped_gpkg.relative_to(ROOT)}`")
    lines.append(f"- Canonical parcel boundary: `{parcel_boundary_path.relative_to(ROOT)}`")
    lines.append(f"- Parcel polygon set: `{parcel_polygons_path.relative_to(ROOT)}`")
    lines.append(f"- Canonical parcel overlay map: `outputs/maps/phase3_parcel_context.html`")

    report_path.write_text("\n".join(lines) + "\n")


def write_map(
    map_path: Path,
    streams_path: Path,
    parcel_boundary_path: Path,
    parcel_polygons_path: Path,
    hazard_path: Path,
    local_aoi_path: Path,
    context_aoi_path: Path,
) -> None:
    streams = _ensure_crs(gpd.read_file(streams_path)).to_crs(4326)
    parcel_boundary = _ensure_crs(gpd.read_file(parcel_boundary_path)).to_crs(4326)
    parcel_polygons = _ensure_crs(gpd.read_file(parcel_polygons_path)).to_crs(4326)
    hazard = _ensure_crs(gpd.read_file(hazard_path)).to_crs(4326)
    local_aoi = _ensure_crs(gpd.read_file(local_aoi_path)).to_crs(4326)
    context_aoi = _ensure_crs(gpd.read_file(context_aoi_path)).to_crs(4326)

    center = parcel_boundary.geometry.iloc[0].centroid
    m = folium.Map(location=[center.y, center.x], zoom_start=16, tiles="CartoDB positron")

    folium.GeoJson(
        hazard,
        name="Mapped flood hazard polygons",
        style_function=_style_hazard,
        tooltip=folium.GeoJsonTooltip(fields=["flood_plai"], aliases=["Class"]),
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
        style_function=_style_parcels,
        tooltip=folium.GeoJsonTooltip(fields=["apn", "situs_address", "situs_street", "situs_suffix"], aliases=["APN", "Number", "Street", "Suffix"]),
    ).add_to(m)

    folium.GeoJson(
        parcel_boundary,
        name="Dissolved parcel boundary",
        style_function=_style_boundary,
        tooltip=folium.GeoJsonTooltip(fields=["name", "parcel_count"], aliases=["Name", "Parcels"]),
    ).add_to(m)

    folium.GeoJson(
        streams,
        name="Selected stream network",
        style_function=_style_streams,
        tooltip=folium.GeoJsonTooltip(fields=[f for f in streams.columns if f != "geometry"], aliases=[f for f in streams.columns if f != "geometry"]),
    ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    map_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(map_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-run overlay metrics with the De Anza Villas parcel boundary wired in.")
    parser.add_argument("--streams", type=Path, default=DEFAULT_STREAMS)
    parser.add_argument("--parcel-boundary", type=Path, default=DEFAULT_PARCEL_BOUNDARY)
    parser.add_argument("--parcel-polygons", type=Path, default=DEFAULT_PARCEL_POLYGONS)
    parser.add_argument("--hazard", type=Path, default=DEFAULT_HAZARD)
    parser.add_argument("--local-aoi", type=Path, default=DEFAULT_LOCAL_AOI)
    parser.add_argument("--context-aoi", type=Path, default=DEFAULT_CONTEXT_AOI)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--map-path", type=Path, default=DEFAULT_MAP_PATH)
    args = parser.parse_args()

    df, metrics_csv, metrics_json, clipped_gpkg = compute_overlay_metrics(
        streams_path=args.streams,
        parcel_boundary_path=args.parcel_boundary,
        parcel_polygons_path=args.parcel_polygons,
        hazard_path=args.hazard,
        local_aoi_path=args.local_aoi,
        context_aoi_path=args.context_aoi,
        outdir=args.outdir,
    )

    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "phase3_parcel_overlay.md"
    write_report(
        df=df,
        report_path=report_path,
        streams_path=args.streams,
        parcel_boundary_path=args.parcel_boundary,
        parcel_polygons_path=args.parcel_polygons,
        hazard_path=args.hazard,
        local_aoi_path=args.local_aoi,
        context_aoi_path=args.context_aoi,
        metrics_csv=metrics_csv,
        metrics_json=metrics_json,
        clipped_gpkg=clipped_gpkg,
    )

    write_map(
        map_path=args.map_path,
        streams_path=clipped_gpkg if clipped_gpkg is not None and clipped_gpkg.exists() else args.streams,
        parcel_boundary_path=args.parcel_boundary,
        parcel_polygons_path=args.parcel_polygons,
        hazard_path=args.hazard,
        local_aoi_path=args.local_aoi,
        context_aoi_path=args.context_aoi,
    )

    print(report_path)
    print(metrics_csv)
    print(metrics_json)
    if clipped_gpkg is not None:
        print(clipped_gpkg)
    print(args.map_path)


if __name__ == "__main__":
    main()
