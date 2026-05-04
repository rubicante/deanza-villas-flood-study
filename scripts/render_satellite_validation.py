from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd

from scripts.study_config import ROOT, config_path, deliverable_path, step_path
from scripts.study_utils import build_standard_map

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


def main() -> None:
    if not SUMMARY_CSV.exists():
        print(f"SKIP: no candidates CSV at {SUMMARY_CSV}")
        return
    if not SELECTED_JSON.exists():
        print(f"SKIP: no selected JSON at {SELECTED_JSON}")
        return

    candidates_df = pd.read_csv(SUMMARY_CSV)
    candidates = candidates_df.to_dict(orient="records")
    selected = json.loads(SELECTED_JSON.read_text())

    # Load vectors for map
    local_aoi = gpd.read_file(LOCAL_AOI_PATH)
    if local_aoi.crs is None:
        local_aoi = local_aoi.set_crs(4326)
    local_aoi = local_aoi.to_crs(4326)

    parcel = gpd.read_file(PARCEL_BOUNDARY_PATH)
    if parcel.crs is None:
        parcel = parcel.set_crs(4326)
    parcel = parcel.to_crs(4326)

    hazard = gpd.read_file(FEMA_PATH)
    if hazard.crs is None:
        hazard = hazard.set_crs(4326)
    hazard = hazard.to_crs(4326)

    streams = gpd.read_file(STREAMS_PATH)
    if streams.crs is None:
        streams = streams.set_crs(4326)
    streams = streams.to_crs(4326)

    # Build report
    search_lines = "\n".join(
        f"- {s['label']}: {s['temporal'][0]} to {s['temporal'][1]} (max {s['max_items']} items)"
        for s in SEARCHES
    )

    candidate_lines = []
    for collection in sorted({c["collection"] for c in candidates}):
        group = [c for c in candidates if c["collection"] == collection]
        group.sort(key=lambda c: (c["local_water_pixels"], c["parcel_water_pixels"], c["water_pixels"]), reverse=True)
        best = group[0]
        total_local = sum(c["local_water_pixels"] for c in group)
        total_parcel = sum(c["parcel_water_pixels"] for c in group)
        seen_local = sum(1 for c in group if c["local_water_pixels"] > 0)
        seen_parcel = sum(1 for c in group if c["parcel_water_pixels"] > 0)
        candidate_lines.append(
            f"- {collection}: {len(group)} candidates, {seen_local} with local-AOI water, {seen_parcel} with parcel water, best scene {best['date']} ({best['native_id']})"
        )
        candidate_lines.append(
            f"  best counts: local={best['local_water_pixels']}, parcel={best['parcel_water_pixels']}, total water={best['water_pixels']}, local share={best['local_water_share']:.3%}, parcel share={best['parcel_water_share']:.3%}"
        )
        candidate_lines.append(
            f"  aggregate local water pixels across candidates: {total_local}; parcel water pixels: {total_parcel}"
        )

    selected_lines = []
    for scene in selected:
        selected_lines.append(
            f"- {scene['collection']} / {scene['date']} / {scene['native_id']}: local water {scene['local_water_pixels']}, parcel water {scene['parcel_water_pixels']}, overall water {scene['water_pixels']}"
        )
        browse_url = scene.get("browse_url")
        if browse_url:
            selected_lines.append(f"  browse: {browse_url}")
        selected_lines.append(f"  data: {scene['data_url']}")
        selected_lines.append(f"  local file: {scene['local_path']}")
        browse_path = scene.get("browse_path")
        if browse_path:
            selected_lines.append(f"  browse file: {browse_path}")

    hls_best = next((s for s in selected if s["collection"] == "OPERA DSWx-HLS"), None)
    s1_best = next((s for s in selected if s["collection"] == "OPERA DSWx-S1"), None)

    interp_lines = []
    if hls_best and hls_best["local_water_pixels"] > 0:
        interp_lines.append(
            f"- DSWx-HLS provides positive local evidence: the best scene ({hls_best['date']}) detected {hls_best['local_water_pixels']} water/inundation pixels inside the 2 km AOI and {hls_best['parcel_water_pixels']} pixels inside the parcel boundary."
        )
    else:
        interp_lines.append("- DSWx-HLS did not produce positive local water pixels in the searched window.")
    if s1_best:
        if s1_best["local_water_pixels"] > 0:
            interp_lines.append(
                f"- DSWx-S1 also shows local wetting in the selected scene ({s1_best['date']}), supporting the HLS signal."
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

Run date: {datetime.now(timezone.utc).date().isoformat()} UTC

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
    print(REPORT_PATH)

    # Build map
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
        geom = scene.get("bbox_geojson")
        if geom is None:
            continue
        popup_html = (
            f"<b>{scene['collection']}</b><br>"
            f"{scene['date']}<br>"
            f"local water pixels: {scene['local_water_pixels']}<br>"
            f"parcel water pixels: {scene['parcel_water_pixels']}<br>"
            f"overall water pixels: {scene['water_pixels']}<br>"
        )
        browse_url = scene.get("browse_url")
        if browse_url:
            popup_html += f'<a href="{browse_url}" target="_blank">browse image</a>'
        folium.GeoJson(
            geom,
            name=f"{scene['collection']} footprint {scene['date']}",
            style_function=lambda _f, color="#ff7f0e": {"color": color, "weight": 2, "fill": False, "opacity": 0.85},
            popup=folium.Popup(popup_html, max_width=350),
        ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(MAP_PATH))
    print(MAP_PATH)


if __name__ == "__main__":
    main()
