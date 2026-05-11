from pathlib import Path
import time

import numpy as np
import py3dep
import rasterio
import rasterio.transform
from rasterio.warp import Resampling, calculate_default_transform
from rasterio.mask import mask as rio_mask
from shapely.ops import unary_union


def _geometry_to_polygon(geometry):
    """Accept GeoJSON path, shapely geometry, or GeoDataFrame."""
    if isinstance(geometry, (str, Path)):
        import geopandas as gpd
        geometry = gpd.read_file(geometry)
    if hasattr(geometry, 'geometry'):
        geometry = unary_union(geometry.geometry.values)
    return geometry


def fetch_dem(
    boundary,
    resolution: float = 1.0,
    crs: str = "EPSG:5070",
    buffer_m: float = 200.0,
    output: Path = Path("dem.tif"),
) -> Path:
    """Fetch DEM via py3dep, reproject to target CRS, clip to buffered boundary."""
    import geopandas as gpd

    boundary = _geometry_to_polygon(boundary)
    gdf_proj = gpd.GeoDataFrame(geometry=[boundary], crs="EPSG:4326").to_crs(crs)
    buffered = gdf_proj.geometry.iloc[0].buffer(buffer_m)

    bbox_4326 = (gpd.GeoDataFrame(geometry=[buffered], crs=crs)
                 .to_crs("EPSG:4326").total_bounds)  # (w, s, e, n)

    t0 = time.time()
    print(f"Fetch: res={resolution}m ...", end=" ", flush=True)
    tile = py3dep.get_dem(tuple(bbox_4326),
                          resolution=int(resolution) if resolution >= 1 else resolution,
                          crs=4326)
    print(f"{time.time() - t0:.0f}s", flush=True)

    tile_data = np.squeeze(tile.values).astype("float32")
    src_h, src_w = tile_data.shape
    src_transform = tile.rio.transform()
    src_crs = tile.rio.crs
    src_bounds = rasterio.transform.array_bounds(src_h, src_w, src_transform)

    dst_transform, dst_w, dst_h = calculate_default_transform(
        src_crs, crs, src_w, src_h, *src_bounds, resolution=resolution)

    dst_data = np.empty((dst_h, dst_w), dtype="float32")
    rasterio.warp.reproject(
        source=tile_data, destination=dst_data,
        src_transform=src_transform, src_crs=src_crs,
        dst_transform=dst_transform, dst_crs=crs,
        src_nodata=-32768.0, dst_nodata=-32768.0,
        resampling=Resampling.bilinear,
    )

    reproj_profile = {
        "driver": "GTiff", "count": 1, "height": dst_h, "width": dst_w,
        "transform": dst_transform, "crs": crs, "dtype": "float32",
        "compress": "lzw", "nodata": -32768.0,
    }
    with rasterio.MemoryFile() as mem:
        with mem.open(**reproj_profile) as ds:
            ds.write(dst_data, 1)
        with mem.open() as ds:
            out_image, out_transform = rio_mask(
                ds, [buffered], crop=True, nodata=-32768.0, filled=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    out_profile = {**reproj_profile,
                   "height": out_image.shape[1], "width": out_image.shape[2],
                   "transform": out_transform}
    with rasterio.open(output, "w", **out_profile) as dst:
        dst.write(out_image[0].astype("float32"), 1)

    n_valid = int(np.sum(out_image[0] != -32768.0))
    print(f"  → {output} ({n_valid / 1e6:.1f}M valid px, "
          f"{output.stat().st_size / 1e6:.0f}MB, {time.time() - t0:.0f}s total)")
    return output
