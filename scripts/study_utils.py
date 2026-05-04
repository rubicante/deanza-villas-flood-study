from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import folium
import geopandas as gpd

from scripts.study_config import TARGET_CRS


def ensure_crs(
    gdf_or_path: gpd.GeoDataFrame | Path,
    crs: str = TARGET_CRS,
) -> gpd.GeoDataFrame:
    """Return a GeoDataFrame in `crs`.

    Accepts either an already-loaded GeoDataFrame or a file path.
    If the GeoDataFrame has no CRS, assumes EPSG:4326.
    """
    gdf = gpd.read_file(gdf_or_path) if isinstance(gdf_or_path, Path) else gdf_or_path
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    return gdf.to_crs(crs)


def read_vector(path: Path, crs: str = TARGET_CRS) -> gpd.GeoDataFrame:
    """Thin alias: load a vector file and reproject to `crs`."""
    return ensure_crs(path, crs)


def read_vectors(crs: str = TARGET_CRS, **named_paths: Path) -> dict[str, gpd.GeoDataFrame]:
    """Load multiple named vector files and reproject all to `crs`.

    Usage::

        vecs = read_vectors(streams=STREAMS_PATH, parcel=PARCEL_PATH)
        streams = vecs["streams"]
    """
    return {name: ensure_crs(path, crs) for name, path in named_paths.items()}


def optional(template: str, value: object) -> str:
    """Return ``template.format(value)`` when value is truthy, else empty string."""
    return template.format(value) if value else ""


def safe_write_json(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def _to_wgs84(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return gdf.to_crs(4326)


def build_standard_map(
    *,
    center_gdf: gpd.GeoDataFrame,
    zoom: int = 15,
    satellite_basemap: bool = False,
    hazard: gpd.GeoDataFrame | None = None,
    context_aoi: gpd.GeoDataFrame | None = None,
    local_aoi: gpd.GeoDataFrame | None = None,
    parcel_polygons: gpd.GeoDataFrame | None = None,
    parcel_boundary: gpd.GeoDataFrame | None = None,
    streams: gpd.GeoDataFrame | None = None,
    streams_inside: gpd.GeoDataFrame | None = None,
    add_layer_control: bool = True,
) -> folium.Map:
    """Build a standard folium map with project layers in canonical order.

    Layers are added bottom-up: hazard, context AOI, local AOI, parcel
    polygons, parcel boundary, streams (all, then inside-parcel highlight).
    Returns the map so callers can add extra layers before saving.
    """
    center = _to_wgs84(center_gdf).geometry.union_all().centroid

    if satellite_basemap:
        m = folium.Map(location=[center.y, center.x], zoom_start=zoom, tiles=None)
        folium.TileLayer("Esri.WorldImagery", name="Satellite imagery", attr="Esri").add_to(m)
        folium.TileLayer("CartoDB positron", name="Light basemap", attr="CartoDB").add_to(m)
    else:
        m = folium.Map(location=[center.y, center.x], zoom_start=zoom, tiles="CartoDB positron")

    if hazard is not None:
        haz = _to_wgs84(hazard)

        def _hazard_style(feature: dict) -> dict:
            cls = feature["properties"].get("flood_plai")
            if cls == "FW100":
                return {"fillColor": "#d7301f", "color": "#a50f15", "weight": 1, "fillOpacity": 0.30}
            return {"fillColor": "#fc8d59", "color": "#d7301f", "weight": 1, "fillOpacity": 0.16}

        tip = (
            folium.GeoJsonTooltip(fields=["flood_plai"], aliases=["Class"])
            if "flood_plai" in haz.columns
            else None
        )
        folium.GeoJson(
            haz,
            name="Mapped flood hazard polygons",
            style_function=_hazard_style,
            tooltip=tip,
        ).add_to(m)

    if context_aoi is not None:
        folium.GeoJson(
            _to_wgs84(context_aoi),
            name="8 km fan context AOI",
            style_function=lambda _f: {"fill": False, "color": "#636363", "weight": 2, "dashArray": "4 4"},
        ).add_to(m)

    if local_aoi is not None:
        folium.GeoJson(
            _to_wgs84(local_aoi),
            name="2 km local AOI",
            style_function=lambda _f: {"fill": False, "color": "#969696", "weight": 2, "dashArray": "2 4"},
        ).add_to(m)

    if parcel_polygons is not None:
        pp = _to_wgs84(parcel_polygons)
        tip_fields = [f for f in ["apn", "situs_address", "situs_street", "situs_suffix", "subname"] if f in pp.columns]
        folium.GeoJson(
            pp,
            name="De Anza Villas parcel polygons",
            style_function=lambda _f: {"fillColor": "#9ecae1", "color": "#3182bd", "weight": 1, "fillOpacity": 0.12},
            tooltip=folium.GeoJsonTooltip(fields=tip_fields, aliases=tip_fields) if tip_fields else None,
        ).add_to(m)

    if parcel_boundary is not None:
        pb = _to_wgs84(parcel_boundary)
        pb_fields = [f for f in ["name", "parcel_count"] if f in pb.columns]
        folium.GeoJson(
            pb,
            name="Dissolved parcel boundary",
            style_function=lambda _f: {"fill": False, "color": "#000000", "weight": 3},
            tooltip=folium.GeoJsonTooltip(fields=pb_fields, aliases=pb_fields) if pb_fields else None,
        ).add_to(m)

    if streams is not None:
        folium.GeoJson(
            _to_wgs84(streams),
            name="Selected channel network",
            style_function=lambda _f: {"color": "#2b8cbe", "weight": 2, "opacity": 0.85},
        ).add_to(m)

    if streams_inside is not None:
        folium.GeoJson(
            _to_wgs84(streams_inside),
            name="Channel network inside parcel",
            style_function=lambda _f: {"color": "#006d2c", "weight": 3, "opacity": 0.95},
        ).add_to(m)

    if add_layer_control:
        folium.LayerControl(collapsed=False).add_to(m)
    return m
