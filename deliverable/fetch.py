"""
DEM fetch: py3dep tile grid → reproject to single target CRS → clip to
buffered boundary polygon → merge.

Key spike lessons:
  - Force float32 + LZW (WBT fill writes float64 otherwise)
  - Single target grid (shared origin) avoids merge-time seams
  - Clip tiles to polygon BEFORE merge (avoids nodata grid padding)
  - Auto-tile: caller sets max_tile_pixels; library derives N_X, N_Y
"""

from pathlib import Path
import time, gc

import numpy as np
import py3dep
import rasterio
from rasterio.warp import transform_bounds, Resampling, calculate_default_transform
from rasterio.merge import merge
from rasterio.mask import mask as rio_mask
from rasterio.transform import from_origin
from shapely.geometry import Polygon
from shapely.ops import unary_union


def _snap_out(v: float, res: float) -> float:
    return np.floor(v / res) * res


def _snap_out_max(v: float, res: float) -> float:
    return np.ceil(v / res) * res


def _geometry_to_polygon(geometry):
    """Accept GeoJSON path, shapely geometry, or GeoDataFrame."""
    if isinstance(geometry, (str, Path)):
        import geopandas as gpd
        geometry = gpd.read_file(geometry)
    if hasattr(geometry, 'geometry'):
        geometry = unary_union(geometry.geometry.values)
    return geometry


def fetch_dem(
    boundary,          # GeoJSON path, shapely geometry, or GeoDataFrame
    resolution: float = 1.0,
    crs: str = "EPSG:5070",
    buffer_m: float = 200.0,
    output: Path = Path("dem.tif"),
    max_tile_pixels: int = 50_000_000,   # auto-tile: max px per py3dep fetch
) -> Path:
    """
    Fetch DEM via py3dep WCS, reproject to target CRS, clip to buffered
    boundary polygon, merge tiles.

    Returns the output Path on success. Raises on failure.
    """
    boundary = _geometry_to_polygon(boundary)

    # Ensure CRS-aware
    import geopandas as gpd
    gdf = gpd.GeoDataFrame(geometry=[boundary], crs="EPSG:4326")
    gdf_work = gdf.to_crs(crs)
    geom = gdf_work.geometry.iloc[0]
    buffered = geom.buffer(buffer_m)

    # Target grid: snap buffered bbox to resolution
    bbox_work = buffered.bounds
    xmin = _snap_out(bbox_work[0], resolution)
    ymin = _snap_out(bbox_work[1], resolution)
    xmax = _snap_out_max(bbox_work[2], resolution)
    ymax = _snap_out_max(bbox_work[3], resolution)
    global_transform = from_origin(xmin, ymax, resolution, resolution)
    width = int((xmax - xmin) / resolution)
    height = int((ymax - ymin) / resolution)

    bbox_4326 = transform_bounds(crs, "EPSG:4326", xmin, ymin, xmax, ymax)

    # Derive tile grid from bbox area
    area_deg2 = (bbox_4326[2] - bbox_4326[0]) * (bbox_4326[3] - bbox_4326[1])
    pixels_per_tile = int(max_tile_pixels)
    n_tiles = max(1, int(np.ceil(area_deg2 * 111320**2 * np.cos(np.radians(
        (bbox_4326[1] + bbox_4326[3]) / 2))**2 / resolution**2 / pixels_per_tile)))
    n_x = max(1, int(np.ceil(np.sqrt(n_tiles * (bbox_4326[2] - bbox_4326[0]) /
                                       (bbox_4326[3] - bbox_4326[1])))))
    n_y = max(1, int(np.ceil(n_tiles / n_x)))

    print(f"Fetch: {width}x{height} ({width*height/1e6:.1f}M px), "
          f"{n_x}x{n_y} tiles, res={resolution}m")

    dx = (bbox_4326[2] - bbox_4326[0]) / n_x
    dy = (bbox_4326[3] - bbox_4326[1]) / n_y
    clipped_tiles = []
    t_total = time.time()

    for row in range(n_y):
        for col in range(n_x):
            w = bbox_4326[0] + col * dx
            e = w + dx
            s = bbox_4326[3] - (row + 1) * dy
            n = s + dy

            t0 = time.time()
            print(f"  Tile [{row},{col}] fetch...", end=" ", flush=True)
            tile = py3dep.get_dem((w, s, e, n), resolution=int(resolution) if resolution >= 1 else resolution, crs=4326)
            raw_path = output.parent / f"_{output.stem}_raw_{row}_{col}.tif"
            tile.rio.to_raster(raw_path)
            print(f"{time.time()-t0:.0f}s", end=" ", flush=True)

            t1 = time.time()
            with rasterio.open(raw_path) as src:
                tile_data = src.read(1)
                src_transform = src.transform
                src_crs = src.crs

            # Compute tile bounds in target CRS
            tile_transform, tw, th = calculate_default_transform(
                src_crs, crs, tile_data.shape[1], tile_data.shape[0],
                *src.bounds, resolution=resolution)

            tile_xmin = _snap_out(tile_transform[2], resolution)
            tile_ymax = _snap_out_max(tile_transform[5], resolution)
            tile_xmax = tile_xmin + tw * resolution
            tile_ymin = tile_ymax - th * resolution
            tile_xmin = max(tile_xmin, xmin)
            tile_ymin = max(tile_ymin, ymin)
            tile_xmax = min(tile_xmax, xmax)
            tile_ymax = min(tile_ymax, ymax)
            tw = max(1, int((tile_xmax - tile_xmin) / resolution))
            th = max(1, int((tile_ymax - tile_ymin) / resolution))
            tile_transform = from_origin(tile_xmin, tile_ymax, resolution, resolution)

            reproj_path = output.parent / f"_{output.stem}_tile_{row}_{col}.tif"
            profile = {"driver": "GTiff", "count": 1, "height": th, "width": tw,
                       "transform": tile_transform, "crs": crs, "dtype": "float32",
                       "compress": "lzw", "nodata": -32768.0}
            with rasterio.open(reproj_path, "w", **profile) as dst:
                rasterio.warp.reproject(
                    source=tile_data, destination=rasterio.band(dst, 1),
                    src_transform=src_transform, src_crs=src_crs,
                    dst_transform=tile_transform, dst_crs=crs,
                    resampling=Resampling.bilinear)
            raw_path.unlink()
            del tile, tile_data
            print(f"reproj {time.time()-t1:.0f}s", end=" ", flush=True)

            # Clip to buffered polygon
            t2 = time.time()
            clip_path = output.parent / f"_{output.stem}_clip_{row}_{col}.tif"
            with rasterio.open(reproj_path) as src:
                out_image, out_transform = rio_mask(
                    src, [buffered], crop=True, nodata=-32768.0, filled=False)
            clip_profile = {"driver": "GTiff", "count": 1,
                            "height": out_image.shape[1], "width": out_image.shape[2],
                            "transform": out_transform, "crs": crs,
                            "dtype": "float32", "compress": "lzw", "nodata": -32768.0}
            with rasterio.open(clip_path, "w", **clip_profile) as dst:
                dst.write(out_image[0], 1)
            reproj_path.unlink()
            clipped_tiles.append(clip_path)
            n_valid = int(np.sum(out_image[0] != -32768.0))
            print(f"clip {time.time()-t2:.0f}s ({n_valid/1e6:.1f}M valid)", flush=True)
            gc.collect()

    # Merge clipped tiles
    print(f"  Merging {len(clipped_tiles)} tiles...", end=" ", flush=True)
    t0 = time.time()
    mosaic, out_transform = merge(clipped_tiles, res=resolution, method="first")
    with rasterio.open(clipped_tiles[0]) as s0:
        ref_profile = {"driver": "GTiff", "count": 1, "crs": s0.crs}
    ref_profile.update(transform=out_transform, width=mosaic.shape[2],
                       height=mosaic.shape[1], dtype="float32",
                       compress="lzw", nodata=-32768.0)
    output.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output, "w", **ref_profile) as dst:
        dst.write(mosaic[0].astype("float32"), 1)
    for ct in clipped_tiles:
        ct.unlink()
    n_valid = int(np.sum(mosaic[0] != -32768.0))
    print(f"{time.time()-t0:.0f}s ({n_valid/1e6:.1f}M valid px, "
          f"{output.stat().st_size/1e6:.0f}MB)")

    del mosaic
    gc.collect()
    print(f"  Total: {time.time()-t_total:.0f}s → {output}")
    return output
