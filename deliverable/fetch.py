from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
import rasterio.transform
from rasterio.mask import mask as rio_mask
from rasterio.merge import merge as rio_merge
from rasterio.warp import Resampling, calculate_default_transform
from rasterio.warp import reproject as rio_reproject
from shapely.ops import unary_union

TNM_API = "https://tnmaccess.nationalmap.gov/api/v1/products"
_DATASET_1M = "Digital Elevation Model (DEM) 1 meter"
NODATA = -32768.0


def _geometry_to_polygon(geometry):
    """Accept GeoJSON path, shapely geometry, or GeoDataFrame."""
    if isinstance(geometry, (str, Path)):
        import geopandas as gpd
        geometry = gpd.read_file(geometry)
    if hasattr(geometry, "geometry"):
        geometry = unary_union(geometry.geometry.values)
    from shapely.geometry.base import BaseGeometry
    assert isinstance(geometry, BaseGeometry)
    return geometry


def _query_tnm(bbox: tuple[float, float, float, float]) -> list[dict]:
    """Return deduplicated 1m DEM tiles covering bbox (w,s,e,n in EPSG:4326).

    When multiple surveys cover the same grid position, the newest is kept.
    Raises RuntimeError if no tiles are found.
    """
    w, s, e, n = bbox
    params = {
        "datasets": _DATASET_1M,
        "bbox": f"{w},{s},{e},{n}",
        "outputFormat": "JSON",
        "max": 100,
    }
    url = TNM_API + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.load(resp)
    items = data.get("items", [])
    if not items:
        raise RuntimeError(
            f"TNM returned no 1m DEM tiles for bbox {bbox}. "
            "Verify coverage at https://apps.nationalmap.gov/downloader/"
        )
    items.sort(key=lambda x: x.get("publicationDate", ""), reverse=True)
    seen: set[str] = set()
    result = []
    for item in items:
        m = re.search(r"x\d+y\d+", item.get("title", ""))
        pos = m.group() if m else item.get("title", "")
        if pos not in seen:
            seen.add(pos)
            result.append(item)
    return result


def _download_tile(url: str, cache_dir: Path) -> Path:
    """Download a tile to cache_dir. Returns path. Skips if already cached."""
    fname = Path(url).name
    dest = cache_dir / fname
    if dest.exists() and dest.stat().st_size > 100_000:
        print(f"  cached: {fname}", flush=True)
        return dest
    print(f"  downloading {fname} ...", end=" ", flush=True)
    t0 = time.time()
    urllib.request.urlretrieve(url, dest)
    mb = dest.stat().st_size / 1e6
    print(f"{mb:.0f} MB in {time.time() - t0:.0f}s", flush=True)
    return dest


def fetch_dem(
    boundary,
    resolution: float = 1.0,
    crs: str = "EPSG:5070",
    buffer_m: float = 200.0,
    output: Path = Path("dem.tif"),
    cache_dir: Path | None = None,
) -> Path:
    """Fetch 1m DEM from USGS TNM, mosaic tiles, reproject to crs, clip to boundary.

    Tiles are cached in data/raw/dem/tiles/ (permanent — TNM tiles never change).
    """
    import geopandas as gpd
    from pyproj import Transformer

    geom = _geometry_to_polygon(boundary)
    gdf_proj = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326").to_crs(crs)
    buffered = gdf_proj.geometry.iloc[0].buffer(buffer_m)

    raw_bounds = (
        gpd.GeoDataFrame(geometry=[buffered], crs=crs)
        .to_crs("EPSG:4326")
        .total_bounds
    )
    bbox_4326: tuple[float, float, float, float] = (
        float(raw_bounds[0]), float(raw_bounds[1]),
        float(raw_bounds[2]), float(raw_bounds[3]),
    )

    if cache_dir is None:
        root = Path(__file__).resolve().parents[1]
        cache_dir = root / "data" / "raw" / "dem" / "tiles"
    cache_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print(f"Fetch: res={resolution}m — querying TNM ...", flush=True)
    tiles_meta = _query_tnm(bbox_4326)
    print(f"  {len(tiles_meta)} tile(s) needed", flush=True)
    tile_paths = [_download_tile(t["downloadURL"], cache_dir) for t in tiles_meta]

    print("  mosaicking ...", end=" ", flush=True)
    datasets = [rasterio.open(p) for p in tile_paths]
    try:
        tile_crs = datasets[0].crs
        tr = Transformer.from_crs("EPSG:4326", tile_crs, always_xy=True)
        w4, s4, e4, n4 = bbox_4326
        xs, ys = tr.transform([w4, e4], [s4, n4])
        tile_bounds = (min(xs), min(ys), max(xs), max(ys))
        mosaic, mosaic_transform = rio_merge(
            datasets, bounds=tile_bounds, nodata=NODATA, method="first",
        )
        mosaic_crs = tile_crs
    finally:
        for ds in datasets:
            ds.close()
    print("done", flush=True)

    mosaic_data = mosaic[0].astype("float32")
    src_h, src_w = mosaic_data.shape

    dst_transform, dst_w, dst_h = calculate_default_transform(
        mosaic_crs, crs, src_w, src_h,
        *rasterio.transform.array_bounds(src_h, src_w, mosaic_transform),
        resolution=resolution,
    )
    assert dst_w is not None and dst_h is not None
    dst_data = np.full((dst_h, dst_w), NODATA, dtype="float32")
    rio_reproject(
        source=mosaic_data, destination=dst_data,
        src_transform=mosaic_transform, src_crs=mosaic_crs,
        dst_transform=dst_transform, dst_crs=crs,
        src_nodata=NODATA, dst_nodata=NODATA,
        resampling=Resampling.bilinear,
    )

    reproj_profile = {
        "driver": "GTiff", "count": 1, "height": dst_h, "width": dst_w,
        "transform": dst_transform, "crs": crs, "dtype": "float32",
        "compress": "lzw", "nodata": NODATA,
    }
    with rasterio.MemoryFile() as mem:
        with mem.open(**reproj_profile) as ds:
            ds.write(dst_data, 1)
        with mem.open() as ds:
            out_image, out_transform = rio_mask(
                ds, [buffered], crop=True, nodata=NODATA, filled=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    out_profile = {
        **reproj_profile,
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform,
    }
    with rasterio.open(output, "w", **out_profile) as dst:
        dst.write(out_image[0].astype("float32"), 1)

    n_valid = int(np.sum(out_image[0] != NODATA))
    print(
        f"  → {output} ({n_valid / 1e6:.1f}M valid px, "
        f"{output.stat().st_size / 1e6:.0f} MB, {time.time() - t0:.0f}s total)"
    )
    return output
