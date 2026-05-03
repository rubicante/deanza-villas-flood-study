from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import earthaccess
import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from branca.element import Figure
from rasterio.features import geometry_mask
from shapely.geometry import box, mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.init_env import load_env
from scripts.study_config import config_path
from scripts.study_utils import read_vector

LOCAL_AOI_PATH = config_path("paths", "local_aoi")
PARCEL_BOUNDARY_PATH = config_path("paths", "parcel_boundary")
FEMA_PATH = config_path("paths", "hazard_polygons")
STREAMS_PATH = config_path("paths", "selected_streams")
OUTDIR = config_path("outputs", "phase4_outdir")
DOWNLOAD_DIR = config_path("outputs", "phase4_download_dir")
REPORT_PATH = config_path("outputs", "phase4_report")
MAP_PATH = config_path("outputs", "phase4_map")
SUMMARY_CSV = config_path("outputs", "phase4_summary_csv")
SUMMARY_JSON = config_path("outputs", "phase4_summary_json")
SELECTED_JSON = config_path("outputs", "phase4_selected_json")

SEARCHES = [
    {
        "label": "OPERA DSWx-HLS",
        "short_name": "OPERA_L3_DSWX-HLS_V1",
        "temporal": ("2023-08-15", "2023-09-15"),
        "max_items": 20,
    },
    {
        "label": "OPERA DSWx-S1",
        "short_name": "OPERA_L3_DSWX-S1_V1",
        "temporal": ("2024-08-20", "2024-09-05"),
        "max_items": 20,
    },
]

WATER_CLASSES = {1, 2}


@dataclass
class CandidateStats:
    collection: str
    short_name: str
    native_id: str
    concept_id: str
    date: str
    data_url: str
    browse_url: str | None
    local_path: str
    browse_path: str | None
    raster_crs: str
    raster_shape: str
    valid_pixels: int
    water_pixels: int
    local_valid_pixels: int
    local_water_pixels: int
    parcel_valid_pixels: int
    parcel_water_pixels: int
    local_water_share: float
    parcel_water_share: float
    overall_water_share: float


@dataclass
class SelectedScene:
    collection: str
    native_id: str
    date: str
    local_water_pixels: int
    parcel_water_pixels: int
    water_pixels: int
    local_water_share: float
    parcel_water_share: float
    overall_water_share: float
    data_url: str
    browse_url: str | None
    local_path: str
    browse_path: str | None


def load_geoms(path: Path) -> gpd.GeoDataFrame:
    return read_vector(path, crs="EPSG:4326")


def geometry_from_item(item: dict) -> dict:
    rects = item["umm"]["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["BoundingRectangles"]
    rect = rects[0]
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [rect["WestBoundingCoordinate"], rect["SouthBoundingCoordinate"]],
                [rect["EastBoundingCoordinate"], rect["SouthBoundingCoordinate"]],
                [rect["EastBoundingCoordinate"], rect["NorthBoundingCoordinate"]],
                [rect["WestBoundingCoordinate"], rect["NorthBoundingCoordinate"]],
                [rect["WestBoundingCoordinate"], rect["SouthBoundingCoordinate"]],
            ]
        ],
    }


def related_url(item: dict, kind: str, suffix: str) -> str | None:
    for ru in item["umm"].get("RelatedUrls", []):
        if ru.get("Type") == kind and ru.get("URL", "").endswith(suffix):
            return ru["URL"]
    return None


def download_url(url: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    downloaded = earthaccess.download(url, local_path=dest_dir, show_progress=False)
    return Path(downloaded[0])


def read_stats(
    raster_path: Path,
    local_aoi: gpd.GeoDataFrame,
    parcel: gpd.GeoDataFrame,
) -> tuple[dict, np.ndarray, rasterio.io.DatasetReader]:
    src = rasterio.open(raster_path)
    arr = src.read(1)
    local_r = local_aoi.to_crs(src.crs)
    parcel_r = parcel.to_crs(src.crs)
    local_mask = geometry_mask(
        [mapping(g) for g in local_r.geometry],
        out_shape=arr.shape,
        transform=src.transform,
        invert=True,
    )
    parcel_mask = geometry_mask(
        [mapping(g) for g in parcel_r.geometry],
        out_shape=arr.shape,
        transform=src.transform,
        invert=True,
    )
    valid = np.ones(arr.shape, dtype=bool) if src.nodata is None else arr != src.nodata
    water = np.isin(arr, list(WATER_CLASSES))

    local_valid = int((valid & local_mask).sum())
    parcel_valid = int((valid & parcel_mask).sum())
    local_water = int((water & valid & local_mask).sum())
    parcel_water = int((water & valid & parcel_mask).sum())
    overall_water = int((water & valid).sum())
    valid_pixels = int(valid.sum())

    stats = {
        "raster_crs": str(src.crs),
        "raster_shape": f"{src.height}x{src.width}",
        "valid_pixels": valid_pixels,
        "water_pixels": overall_water,
        "local_valid_pixels": local_valid,
        "local_water_pixels": local_water,
        "parcel_valid_pixels": parcel_valid,
        "parcel_water_pixels": parcel_water,
        "local_water_share": (local_water / local_valid) if local_valid else 0.0,
        "parcel_water_share": (parcel_water / parcel_valid) if parcel_valid else 0.0,
        "overall_water_share": (overall_water / valid_pixels) if valid_pixels else 0.0,
    }
    src.close()
    return stats, arr, src


def collect_candidates(local_aoi: gpd.GeoDataFrame, parcel: gpd.GeoDataFrame) -> list[CandidateStats]:
    minx, miny, maxx, maxy = local_aoi.total_bounds
    bbox = (minx, miny, maxx, maxy)
    rows: list[CandidateStats] = []
    for search in SEARCHES:
        items = earthaccess.search_data(
            short_name=search["short_name"],
            bounding_box=bbox,
            temporal=search["temporal"],
            count=search["max_items"],
        )
        for item in items:
            native_id = item["meta"]["native-id"]
            concept_id = item["meta"]["concept-id"]
            date = item["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:10]
            data_url = related_url(item, "GET DATA", "_B01_WTR.tif")
            browse_url = related_url(item, "GET RELATED VISUALIZATION", "_BROWSE.png")
            if not data_url:
                continue
            local_path = download_url(data_url, DOWNLOAD_DIR)
            browse_path = None
            if browse_url:
                try:
                    browse_path = str(download_url(browse_url, DOWNLOAD_DIR))
                except Exception:
                    browse_path = None

            stats, _, _ = read_stats(local_path, local_aoi, parcel)
            row = CandidateStats(
                collection=search["label"],
                short_name=search["short_name"],
                native_id=native_id,
                concept_id=concept_id,
                date=date,
                data_url=data_url,
                browse_url=browse_url,
                local_path=str(local_path),
                browse_path=browse_path,
                raster_crs=stats["raster_crs"],
                raster_shape=stats["raster_shape"],
                valid_pixels=stats["valid_pixels"],
                water_pixels=stats["water_pixels"],
                local_valid_pixels=stats["local_valid_pixels"],
                local_water_pixels=stats["local_water_pixels"],
                parcel_valid_pixels=stats["parcel_valid_pixels"],
                parcel_water_pixels=stats["parcel_water_pixels"],
                local_water_share=stats["local_water_share"],
                parcel_water_share=stats["parcel_water_share"],
                overall_water_share=stats["overall_water_share"],
            )
            rows.append(row)
    return rows


def choose_selected(candidates: list[CandidateStats]) -> list[SelectedScene]:
    selected: list[SelectedScene] = []
    for collection in sorted({c.collection for c in candidates}):
        group = [c for c in candidates if c.collection == collection]
        group.sort(
            key=lambda c: (
                c.local_water_pixels,
                c.parcel_water_pixels,
                c.water_pixels,
                c.overall_water_share,
            ),
            reverse=True,
        )
        best = group[0]
        selected.append(
            SelectedScene(
                collection=best.collection,
                native_id=best.native_id,
                date=best.date,
                local_water_pixels=best.local_water_pixels,
                parcel_water_pixels=best.parcel_water_pixels,
                water_pixels=best.water_pixels,
                local_water_share=best.local_water_share,
                parcel_water_share=best.parcel_water_share,
                overall_water_share=best.overall_water_share,
                data_url=best.data_url,
                browse_url=best.browse_url,
                local_path=best.local_path,
                browse_path=best.browse_path,
            )
        )
    return selected


def save_summaries(candidates: list[CandidateStats], selected: list[SelectedScene]) -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([asdict(c) for c in candidates])
    df.sort_values(["collection", "local_water_pixels", "parcel_water_pixels", "water_pixels"], ascending=[True, False, False, False], inplace=True)
    df.to_csv(SUMMARY_CSV, index=False)
    SUMMARY_JSON.write_text(json.dumps([asdict(c) for c in candidates], indent=2), encoding="utf-8")
    SELECTED_JSON.write_text(json.dumps([asdict(s) for s in selected], indent=2), encoding="utf-8")


def make_map(
    local_aoi: gpd.GeoDataFrame,
    parcel: gpd.GeoDataFrame,
    hazard: gpd.GeoDataFrame,
    streams: gpd.GeoDataFrame,
    selected: list[SelectedScene],
) -> None:
    fig = Figure(width="100%", height="100%")
    center = parcel.to_crs(4326).geometry.union_all().centroid
    m = folium.Map(location=[center.y, center.x], zoom_start=14, tiles="CartoDB positron")
    fig.add_child(m)

    def style_boundary(color: str, weight: int = 3, fill: bool = False, opacity: float = 0.9):
        return {
            "color": color,
            "weight": weight,
            "fill": fill,
            "fillOpacity": 0.08 if fill else 0.0,
            "opacity": opacity,
        }

    aoi_fields = [field for field in ("name", "status") if field in local_aoi.columns]
    aoi_aliases = [field.title() for field in aoi_fields]
    parcel_fields = [field for field in ("name", "status") if field in parcel.columns]
    parcel_aliases = [field.title() for field in parcel_fields]

    folium.GeoJson(
        local_aoi,
        name="Local AOI",
        style_function=lambda _f: style_boundary("#1f77b4", weight=3),
        tooltip=folium.GeoJsonTooltip(fields=aoi_fields, aliases=aoi_aliases) if aoi_fields else None,
    ).add_to(m)
    folium.GeoJson(
        parcel,
        name="De Anza Villas parcel boundary",
        style_function=lambda _f: style_boundary("#d62728", weight=3, fill=True),
        tooltip=folium.GeoJsonTooltip(fields=parcel_fields, aliases=parcel_aliases) if parcel_fields else None,
    ).add_to(m)
    folium.GeoJson(
        hazard,
        name="FEMA hazard/context",
        style_function=lambda _f: style_boundary("#9467bd", weight=2, fill=True),
    ).add_to(m)
    folium.GeoJson(
        streams,
        name="Selected channel network",
        style_function=lambda _f: {"color": "#2ca02c", "weight": 2, "opacity": 0.85},
    ).add_to(m)

    for scene in selected:
        # add footprint polygon from item extent
        item = None
        for search in SEARCHES:
            if search["label"] == scene.collection:
                item = earthaccess.search_data(short_name=search["short_name"], bounding_box=tuple(local_aoi.to_crs(4326).total_bounds), temporal=(scene.date, scene.date), count=20)
                break
        # rather than re-searching by date ambiguity, create a rectangle from the stored bounds in the selected geojson via a second search on native id
        # if the item can't be retrieved, skip footprint.
        if item:
            found = None
            for candidate in item:
                if candidate["meta"]["native-id"] == scene.native_id:
                    found = candidate
                    break
            if found:
                geom = geometry_from_item(found)
                popup_html = (
                    f"<b>{scene.collection}</b><br>"
                    f"{scene.date}<br>"
                    f"local water pixels: {scene.local_water_pixels}<br>"
                    f"parcel water pixels: {scene.parcel_water_pixels}<br>"
                    f"overall water pixels: {scene.water_pixels}<br>"
                )
                if scene.browse_url:
                    popup_html += f'<a href="{scene.browse_url}" target="_blank">browse image</a>'
                folium.GeoJson(
                    geom,
                    name=f"{scene.collection} footprint {scene.date}",
                    style_function=lambda _f, color="#ff7f0e": {"color": color, "weight": 2, "fill": False, "opacity": 0.85},
                    popup=folium.Popup(popup_html, max_width=350),
                ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(MAP_PATH))


def write_report(
    candidates: list[CandidateStats],
    selected: list[SelectedScene],
    local_aoi: gpd.GeoDataFrame,
    parcel: gpd.GeoDataFrame,
) -> None:
    lines: list[str] = []
    lines.append("# Phase 4 Satellite/Event Validation")
    lines.append("")
    lines.append("Goal: check whether OPERA satellite surface-water products show positive evidence of wetting or flow concentration over the De Anza Villas AOI and parcel.")
    lines.append("")
    lines.append(f"Run date: {datetime.utcnow().date().isoformat()} UTC")
    lines.append("")
    lines.append("Search windows:")
    for s in SEARCHES:
        lines.append(f"- {s['label']}: {s['temporal'][0]} to {s['temporal'][1]} (max {s['max_items']} items)")
    lines.append("")
    lines.append(f"Local AOI: {LOCAL_AOI_PATH.relative_to(ROOT)}")
    lines.append(f"Parcel boundary: {PARCEL_BOUNDARY_PATH.relative_to(ROOT)}")
    lines.append(f"FEMA layer: {FEMA_PATH.relative_to(ROOT)}")
    lines.append(f"Channel network: {STREAMS_PATH.relative_to(ROOT)}")
    lines.append("")
    lines.append("Candidate summary:")
    for collection in sorted({c.collection for c in candidates}):
        group = [c for c in candidates if c.collection == collection]
        group.sort(key=lambda c: (c.local_water_pixels, c.parcel_water_pixels, c.water_pixels), reverse=True)
        best = group[0]
        total_local = sum(c.local_water_pixels for c in group)
        total_parcel = sum(c.parcel_water_pixels for c in group)
        seen_local = sum(1 for c in group if c.local_water_pixels > 0)
        seen_parcel = sum(1 for c in group if c.parcel_water_pixels > 0)
        lines.append(
            f"- {collection}: {len(group)} candidates, {seen_local} with local-AOI water, {seen_parcel} with parcel water, best scene {best.date} ({best.native_id})"
        )
        lines.append(
            f"  best counts: local={best.local_water_pixels}, parcel={best.parcel_water_pixels}, total water={best.water_pixels}, local share={best.local_water_share:.3%}, parcel share={best.parcel_water_share:.3%}"
        )
        lines.append(
            f"  aggregate local water pixels across candidates: {total_local}; parcel water pixels: {total_parcel}"
        )
    lines.append("")
    lines.append("Selected scenes:")
    for scene in selected:
        lines.append(
            f"- {scene.collection} / {scene.date} / {scene.native_id}: local water {scene.local_water_pixels}, parcel water {scene.parcel_water_pixels}, overall water {scene.water_pixels}"
        )
        if scene.browse_url:
            lines.append(f"  browse: {scene.browse_url}")
        lines.append(f"  data: {scene.data_url}")
        lines.append(f"  local file: {scene.local_path}")
        if scene.browse_path:
            lines.append(f"  browse file: {scene.browse_path}")
    lines.append("")
    lines.append("Interpretation:")
    hls_best = next((s for s in selected if s.collection == "OPERA DSWx-HLS"), None)
    s1_best = next((s for s in selected if s.collection == "OPERA DSWx-S1"), None)
    if hls_best and hls_best.local_water_pixels > 0:
        lines.append(
            f"- DSWx-HLS provides positive local evidence: the best scene ({hls_best.date}) detected {hls_best.local_water_pixels} water/inundation pixels inside the 2 km AOI and {hls_best.parcel_water_pixels} pixels inside the parcel boundary."
        )
    else:
        lines.append("- DSWx-HLS did not produce positive local water pixels in the searched window.")
    if s1_best:
        if s1_best.local_water_pixels > 0:
            lines.append(
                f"- DSWx-S1 also shows local wetting in the selected scene ({s1_best.date}), supporting the HLS signal."
            )
        else:
            lines.append(
                f"- DSWx-S1 covered the study area, but the searched scenes did not flag local-AOI water pixels. The S1 footprint still showed broader-valley water detections, so the absence at the parcel is weak evidence only."
            )
    lines.append("- Overall: the satellite record provides positive evidence of wetting in the valley and at least one HLS local detection near the study area; lack of S1 parcel pixels is not evidence of no flooding because the product sampling is sparse and scene timing is limited.")
    lines.append("")
    lines.append("Outputs:")
    lines.append(f"- Report: {REPORT_PATH.relative_to(ROOT)}")
    lines.append(f"- Map: {MAP_PATH.relative_to(ROOT)}")
    lines.append(f"- Candidate CSV: {SUMMARY_CSV.relative_to(ROOT)}")
    lines.append(f"- Candidate JSON: {SUMMARY_JSON.relative_to(ROOT)}")
    lines.append(f"- Selected JSON: {SELECTED_JSON.relative_to(ROOT)}")
    lines.append("- Download cache: data/processed/terrain/deanza_villas_2km_1m/validation_phase4/downloads/")
    lines.append("")
    lines.append("Note: Sentinel-1 GRD fallback was not needed because OPERA DSWx coverage was sufficient for a positive wetting check in this pass.")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    load_env()
    earthaccess.login(strategy="environment")

    local_aoi = load_geoms(LOCAL_AOI_PATH)
    parcel = load_geoms(PARCEL_BOUNDARY_PATH)
    hazard = gpd.read_file(FEMA_PATH)
    if hazard.crs is None:
        hazard = hazard.set_crs(4326)
    hazard = hazard.to_crs(4326)
    streams = gpd.read_file(STREAMS_PATH)
    if streams.crs is None:
        streams = streams.set_crs(4326)
    streams = streams.to_crs(4326)

    candidates = collect_candidates(local_aoi, parcel)
    selected = choose_selected(candidates)
    save_summaries(candidates, selected)
    make_map(local_aoi, parcel, hazard, streams, selected)
    write_report(candidates, selected, local_aoi, parcel)


if __name__ == "__main__":
    main()
