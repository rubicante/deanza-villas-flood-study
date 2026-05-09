"""
Stream extraction and generic export.

Key spike lessons:
  - WBT extract_streams with zero_background=True
  - Keep export format generic (GeoJSON). Project-specific binary in _pipeline.py
"""

from pathlib import Path
import time, json
import numpy as np
import rasterio
import geopandas as gpd
from shapely.geometry import Point
from whitebox.whitebox_tools import WhiteboxTools


def extract_streams(
    accum: Path,
    threshold: int = 250,
    output: Path = Path("streams.tif"),
) -> Path:
    """
    Extract stream raster via WBT extract_streams.
    Returns output Path with binary (0/1) stream mask.
    """
    accum = Path(accum).resolve()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    wbt = WhiteboxTools()
    wbt.set_working_dir(str(output.parent))
    wbt.set_verbose_mode(False)

    t0 = time.time()
    wbt.extract_streams(str(accum), str(output), threshold, zero_background=True)
    if not output.exists():
        raise RuntimeError(f"WBT extract_streams failed: {output} not found")

    with rasterio.open(output) as src:
        n_stream = int((src.read(1) > 0).sum())
    print(f"  Extract streams t={threshold}: {time.time()-t0:.0f}s ({n_stream:,} cells)")
    return output


def export_geojson(
    streams: Path,
    accum: Path,
    output: Path = Path("streams.geojson"),
    target_crs: str = "EPSG:4326",
    max_cells: int | None = None,
) -> Path:
    """
    Export stream cells as GeoJSON of points with accumulation values.

    Each feature: {"accum": value, "lon": x, "lat": y}. Sorted descending
    by accumulation. max_cells limits export size (None = all).
    """
    streams = Path(streams).resolve()
    accum = Path(accum).resolve()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(streams) as src:
        sdata = src.read(1)
        transform_s = src.transform
        src_crs = src.crs
    with rasterio.open(accum) as src:
        accum_data = src.read(1)

    from rasterio.warp import transform as rio_transform

    rows, cols = np.where(sdata > 0)
    n_cells = len(rows)

    xs = transform_s.c + (cols + 0.5) * transform_s.a
    ys = transform_s.f + (rows + 0.5) * transform_s.e
    lons, lats = rio_transform(src_crs, target_crs, xs, ys)
    lons = np.asarray(lons, dtype="float64")
    lats = np.asarray(lats, dtype="float64")

    accums = accum_data[rows, cols]
    order = np.argsort(accums)[::-1]
    if max_cells and max_cells < n_cells:
        order = order[:max_cells]
        n_cells = max_cells

    accums = accums[order]
    lons = lons[order]
    lats = lats[order]

    features = []
    for i in range(n_cells):
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(lons[i]), float(lats[i])]},
            "properties": {"accum": float(accums[i])},
        })

    geojson = {"type": "FeatureCollection", "features": features}
    with open(output, "w") as f:
        json.dump(geojson, f)

    print(f"  GeoJSON: {n_cells:,} features → {output} ({output.stat().st_size/1e6:.1f}MB)")
    return output
