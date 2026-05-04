from __future__ import annotations

import geopandas as gpd
import folium

from scripts.study_config import config_path, step_path

AOI_PATH = config_path("paths", "context_aoi")
FLOOD_PATH = config_path("paths", "hazard_polygons")
OUT_PATH = step_path("terrain_context", "map")


def main() -> None:
    aoi = gpd.read_file(AOI_PATH)
    flood = gpd.read_file(FLOOD_PATH)

    if aoi.crs is None:
        aoi = aoi.set_crs(4326)
    if flood.crs is None:
        flood = flood.set_crs(4326)

    aoi = aoi.to_crs(4326)
    flood = flood.to_crs(4326)

    center = aoi.geometry.iloc[0].centroid
    m = folium.Map(location=[center.y, center.x], zoom_start=10, tiles="CartoDB positron")

    def style_aoi(_feature):
        return {
            "fill": False,
            "color": "black",
            "weight": 3,
        }

    def style_flood(feature):
        cls = feature["properties"].get("flood_plai")
        if cls == "FW100":
            return {"fillColor": "#d7301f", "color": "#a50f15", "weight": 1, "fillOpacity": 0.35}
        return {"fillColor": "#2b8cbe", "color": "#08519c", "weight": 1, "fillOpacity": 0.20}

    folium.GeoJson(
        flood,
        name="San Diego County flood hazard polygons",
        style_function=style_flood,
        tooltip=folium.GeoJsonTooltip(fields=["flood_plai"], aliases=["Class"]),
    ).add_to(m)

    folium.GeoJson(
        aoi,
        name="Terrain context AOI",
        style_function=style_aoi,
        tooltip=folium.GeoJsonTooltip(fields=["name", "status"], aliases=["Name", "Status"]),
    ).add_to(m)

    folium.Marker(
        [33.255, -116.375],
        tooltip="Borrego Springs (approx.)",
        icon=folium.Icon(color="green", icon="home"),
    ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    m.save(OUT_PATH)
    print(OUT_PATH)


if __name__ == "__main__":
    main()
