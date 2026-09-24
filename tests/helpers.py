"""Shared fixtures-as-functions for synthetic rasters (EPSG:5070)."""

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform as rio_transform

# A grid origin near Borrego Springs
X0, Y0 = -1_875_000.0, 1_340_000.0


def write_raster(path: Path, data: np.ndarray, res: float = 10.0,
                 nodata: float | None = None) -> Path:
    prof = {"driver": "GTiff", "height": data.shape[0], "width": data.shape[1],
            "count": 1, "dtype": data.dtype, "crs": "EPSG:5070",
            "transform": from_origin(X0, Y0, res, res), "nodata": nodata}
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(data, 1)
    return path


def box_5070(r0: int, c0: int, r1: int, c1: int, res: float = 10.0):
    """Shapely box covering cells rows r0..r1-1, cols c0..c1-1 (inset 1 m)."""
    from shapely.geometry import box
    return box(X0 + c0 * res + 1, Y0 - r1 * res + 1, X0 + c1 * res - 1, Y0 - r0 * res - 1)


def write_geojson_4326(path: Path, geom_5070) -> Path:
    xs, ys = geom_5070.exterior.coords.xy
    lons, lats = rio_transform("EPSG:5070", "EPSG:4326", list(xs), list(ys))
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {},
        "geometry": {"type": "Polygon",
                     "coordinates": [[list(p) for p in zip(lons, lats)]]}}]}))
    return path
