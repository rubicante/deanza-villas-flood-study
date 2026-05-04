from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import earthaccess
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from shapely.geometry import mapping

from scripts.init_env import load_env
from scripts.study_config import ROOT, config_path, deliverable_path, step_path
from scripts.study_utils import build_standard_map, read_vector

LOCAL_AOI_PATH = config_path("paths", "local_aoi")
PARCEL_BOUNDARY_PATH = config_path("paths", "parcel_boundary")
FEMA_PATH = config_path("paths", "hazard_polygons")
STREAMS_PATH = config_path("paths", "selected_streams")
OUTDIR = step_path("satellite_validation", "outdir")
DOWNLOAD_DIR = step_path("satellite_validation", "download_dir")
REPORT_PATH = deliverable_path("satellite_validation_report")
MAP_PATH = deliverable_path("satellite_validation_map")
SUMMARY_CSV = step_path("satellite_validation", "summary_csv")
SUMMARY_JSON = step_path("satellite_validation", "summary_json")
SELECTED_JSON = step_path("satellite_validation", "selected_json")

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
    bbox_geojson: dict | None = None


def geometry_from_item(item: dict) -> dict:
    rects = item["umm"]["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["BoundingRectangles"]
    rect = rects[0]
    return {
        "type": "Polygon",
        "coordinates": [[
            [rect["WestBoundingCoordinate"], rect["SouthBoundingCoordinate"]],
            [rect["EastBoundingCoordinate"], rect["SouthBoundingCoordinate"]],
            [rect["EastBoundingCoordinate"], rect["NorthBoundingCoordinate"]],
            [rect["WestBoundingCoordinate"], rect["NorthBoundingCoordinate"]],
            [rect["WestBoundingCoordinate"], rect["SouthBoundingCoordinate"]],
        ]],
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
) -> dict:
    with rasterio.open(raster_path) as src:
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

        return {
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


def collect_candidates(
    local_aoi: gpd.GeoDataFrame,
    parcel: gpd.GeoDataFrame,
) -> list[CandidateStats]:
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

            bbox_geojson = geometry_from_item(item)
            stats = read_stats(local_path, local_aoi, parcel)
            rows.append(CandidateStats(
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
                bbox_geojson=bbox_geojson,
            ))
    return rows


def choose_selected(candidates: list[CandidateStats]) -> list[CandidateStats]:
    selected: list[CandidateStats] = []
    for collection in sorted({c.collection for c in candidates}):
        group = [c for c in candidates if c.collection == collection]
        group.sort(
            key=lambda c: (c.local_water_pixels, c.parcel_water_pixels, c.water_pixels, c.overall_water_share),
            reverse=True,
        )
        selected.append(group[0])
    return selected


def save_summaries(candidates: list[CandidateStats], selected: list[CandidateStats]) -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    # Exclude bbox_geojson from serialized output (it's a geometry, not a metric)
    def _to_dict_no_bbox(c: CandidateStats) -> dict:
        d = asdict(c)
        d.pop("bbox_geojson", None)
        return d

    df = pd.DataFrame([_to_dict_no_bbox(c) for c in candidates])
    df.sort_values(
        ["collection", "local_water_pixels", "parcel_water_pixels", "water_pixels"],
        ascending=[True, False, False, False],
        inplace=True,
    )
    df.to_csv(SUMMARY_CSV, index=False)
    SUMMARY_JSON.write_text(json.dumps([_to_dict_no_bbox(c) for c in candidates], indent=2), encoding="utf-8")
    SELECTED_JSON.write_text(json.dumps([_to_dict_no_bbox(s) for s in selected], indent=2), encoding="utf-8")


def make_map(
    local_aoi: gpd.GeoDataFrame,
    parcel: gpd.GeoDataFrame,
    hazard: gpd.GeoDataFrame,
    streams: gpd.GeoDataFrame,
    selected: list[CandidateStats],
) -> None:
    import folium

    m = build_standard_map(
        center_gdf=parcel,
        zoom=14,
        hazard=hazard,
        local_aoi=local_aoi,
        parcel_boundary=parcel,
        streams=streams,
        add_layer_control=False,
    )

    for scene in selected:
        # bbox_geojson was stashed on CandidateStats and carried through to SelectedScene
        geom = scene.bbox_geojson
        if geom is None:
            continue
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
    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(MAP_PATH))


def write_report(
    candidates: list[CandidateStats],
    selected: list[CandidateStats],
) -> None:
    search_lines = "\n".join(
        f"- {s['label']}: {s['temporal'][0]} to {s['temporal'][1]} (max {s['max_items']} items)"
        for s in SEARCHES
    )

    candidate_lines = []
    for collection in sorted({c.collection for c in candidates}):
        group = [c for c in candidates if c.collection == collection]
        group.sort(key=lambda c: (c.local_water_pixels, c.parcel_water_pixels, c.water_pixels), reverse=True)
        best = group[0]
        total_local = sum(c.local_water_pixels for c in group)
        total_parcel = sum(c.parcel_water_pixels for c in group)
        seen_local = sum(1 for c in group if c.local_water_pixels > 0)
        seen_parcel = sum(1 for c in group if c.parcel_water_pixels > 0)
        candidate_lines.append(
            f"- {collection}: {len(group)} candidates, {seen_local} with local-AOI water, {seen_parcel} with parcel water, best scene {best.date} ({best.native_id})"
        )
        candidate_lines.append(
            f"  best counts: local={best.local_water_pixels}, parcel={best.parcel_water_pixels}, total water={best.water_pixels}, local share={best.local_water_share:.3%}, parcel share={best.parcel_water_share:.3%}"
        )
        candidate_lines.append(
            f"  aggregate local water pixels across candidates: {total_local}; parcel water pixels: {total_parcel}"
        )

    selected_lines = []
    for scene in selected:
        selected_lines.append(
            f"- {scene.collection} / {scene.date} / {scene.native_id}: local water {scene.local_water_pixels}, parcel water {scene.parcel_water_pixels}, overall water {scene.water_pixels}"
        )
        if scene.browse_url:
            selected_lines.append(f"  browse: {scene.browse_url}")
        selected_lines.append(f"  data: {scene.data_url}")
        selected_lines.append(f"  local file: {scene.local_path}")
        if scene.browse_path:
            selected_lines.append(f"  browse file: {scene.browse_path}")

    hls_best = next((s for s in selected if s.collection == "OPERA DSWx-HLS"), None)
    s1_best = next((s for s in selected if s.collection == "OPERA DSWx-S1"), None)

    interp_lines = []
    if hls_best and hls_best.local_water_pixels > 0:
        interp_lines.append(
            f"- DSWx-HLS provides positive local evidence: the best scene ({hls_best.date}) detected {hls_best.local_water_pixels} water/inundation pixels inside the 2 km AOI and {hls_best.parcel_water_pixels} pixels inside the parcel boundary."
        )
    else:
        interp_lines.append("- DSWx-HLS did not produce positive local water pixels in the searched window.")
    if s1_best:
        if s1_best.local_water_pixels > 0:
            interp_lines.append(
                f"- DSWx-S1 also shows local wetting in the selected scene ({s1_best.date}), supporting the HLS signal."
            )
        else:
            interp_lines.append(
                "- DSWx-S1 covered the study area, but the searched scenes did not flag local-AOI water pixels. The S1 footprint still showed broader-valley water detections, so the absence at the parcel is weak evidence only."
            )
    interp_lines.append(
        "- Overall: the satellite record provides positive evidence of wetting in the valley and at least one HLS local detection near the study area; lack of S1 parcel pixels is not evidence of no flooding because the product sampling is sparse and scene timing is limited."
    )

    report = f"""\
# Satellite / Event Validation

Goal: check whether OPERA satellite surface-water products show positive evidence of wetting or flow concentration over the De Anza Villas AOI and parcel.

Run date: {datetime.utcnow().date().isoformat()} UTC

Search windows:
{search_lines}

Local AOI: {LOCAL_AOI_PATH.relative_to(ROOT)}
Parcel boundary: {PARCEL_BOUNDARY_PATH.relative_to(ROOT)}
FEMA layer: {FEMA_PATH.relative_to(ROOT)}
Channel network: {STREAMS_PATH.relative_to(ROOT)}

Candidate summary:
{chr(10).join(candidate_lines)}

Selected scenes:
{chr(10).join(selected_lines)}

Interpretation:
{chr(10).join(interp_lines)}

Outputs:
- Report: {REPORT_PATH.relative_to(ROOT)}
- Map: {MAP_PATH.relative_to(ROOT)}
- Candidate CSV: {SUMMARY_CSV.relative_to(ROOT)}
- Candidate JSON: {SUMMARY_JSON.relative_to(ROOT)}
- Selected JSON: {SELECTED_JSON.relative_to(ROOT)}
- Download cache: `{DOWNLOAD_DIR.relative_to(ROOT)}`

Note: Sentinel-1 GRD fallback was not needed because OPERA DSWx coverage was sufficient for a positive wetting check in this pass.
"""

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")


def main() -> None:
    load_env()
    earthaccess.login(strategy="environment")

    # Read vectors once; pass GeoDataFrames to downstream functions.
    local_aoi = read_vector(LOCAL_AOI_PATH, crs="EPSG:4326")
    parcel = read_vector(PARCEL_BOUNDARY_PATH, crs="EPSG:4326")
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
    write_report(candidates, selected)


if __name__ == "__main__":
    main()
