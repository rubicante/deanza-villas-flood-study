"""Small vector↔raster helpers shared across the pipeline."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
from rasterio import features
from shapely.ops import unary_union


def polygon_mask(vector: Path | gpd.GeoDataFrame, crs, transform, shape) -> np.ndarray:
    """Rasterize the union of all features in `vector` onto a grid.

    Returns a uint8 mask (1 inside). Every feature counts: a multi-feature
    boundary is never cropped to its first feature."""
    gdf = gpd.read_file(vector) if isinstance(vector, (str, Path)) else vector
    geom = unary_union(gdf.to_crs(crs).geometry.values)
    return features.rasterize([(geom, 1)], out_shape=shape, transform=transform, dtype="uint8")
