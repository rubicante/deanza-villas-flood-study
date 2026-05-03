from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from scripts.study_config import TARGET_CRS


def read_vector(path: Path, crs: str = TARGET_CRS) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    return gdf.to_crs(crs)


def ensure_crs(gdf: gpd.GeoDataFrame, crs: str = TARGET_CRS) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    return gdf.to_crs(crs)


def safe_write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def safe_write_json(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def line_style(color: str, weight: int = 2, opacity: float = 0.85, dash_array: str | None = None, fill: bool = False, fill_opacity: float = 0.08) -> dict[str, Any]:
    style: dict[str, Any] = {
        "color": color,
        "weight": weight,
        "opacity": opacity,
        "fill": fill,
        "fillOpacity": fill_opacity if fill else 0.0,
    }
    if dash_array:
        style["dashArray"] = dash_array
    return style


def polygon_style(fill_color: str, color: str, weight: int = 1, fill_opacity: float = 0.12) -> dict[str, Any]:
    return {
        "fillColor": fill_color,
        "color": color,
        "weight": weight,
        "fillOpacity": fill_opacity,
    }
