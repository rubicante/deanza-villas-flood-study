"""
Watershed delineation from a DEM + pour-point geometry.

Key spike lessons:
  - DEM extent must cover full upstream contributing area or boundary is
    silently truncated (Henderson narrow DEM → 33.6 km²; wide DEM → 107 km²)
  - rasterio features.shapes/rasterize require int16 raster + uint8 mask
  - WBT watershed() does not need snap_pour_points on fan surfaces; snap
    requires a stream threshold, which is terrain-dependent
  - shapely unary_union + simplify is order-sensitive; output is
    geometrically equivalent but not byte-identical across reruns
"""

from pathlib import Path
import time
import warnings

import numpy as np
import rasterio
from rasterio import features
from shapely.geometry import shape
from shapely.ops import unary_union
import geopandas as gpd
from whitebox.whitebox_tools import WhiteboxTools


def delineate_watershed(
    dem: Path,
    pour_geometry_path: Path,
    output_boundary: Path,
    output_boundary_5070: Path | None = None,
    *,
    snap_distance_m: float | None = None,
    snap_stream_threshold: int = 100,
    keep_intermediates: bool = False,
) -> gpd.GeoDataFrame:
    """
    Delineate the watershed draining to a set of pour points.

    Parameters
    ----------
    dem : Path
        Path to a filled DEM (caller is responsible for breach+fill).
    pour_geometry_path : Path
        Path to a GeoJSON file containing pour-point geometry. Can be any
        geometry type — points rasterize to single cells, polygons rasterize
        to filled regions. The function loads and reprojects to match the
        DEM CRS.
    output_boundary : Path
        Path for the WGS84 GeoJSON output.
    output_boundary_5070 : Path or None
        Optional path for an EPSG:5070 copy.
    snap_distance_m : float or None
        None (default) = rasterized pour cells used directly. Pass a
        positive value to snap pour points to the nearest stream cell
        within that distance before watershed delineation. Snapping
        requires selecting a stream threshold (snap_stream_threshold) and
        the correct threshold is terrain-dependent — a wrong default would
        produce silently wrong watersheds. Explicit opt-in forces the
        caller to tune.
    snap_stream_threshold : int
        D8 accumulation threshold for stream-cell identification used in
        snapping. Only consumed when snap_distance_m is set. Default 100.
    keep_intermediates : bool
        If True, keep the D8 pointer and watershed raster on disk for
        debugging. Default False.

    Returns
    -------
    gpd.GeoDataFrame
        The WGS84 watershed boundary polygon with an `area_km2` property.

    Raises
    ------
    ValueError
        If the pour geometry does not overlap the DEM extent after
        reprojection.

    Notes
    -----
    The DEM extent must cover the full contributing area upstream of the
    pour points. If the DEM is too narrow, the watershed boundary will be
    clipped at the DEM edge — a silent incorrect result. This function
    warns when the boundary bbox touches the DEM edge. For Henderson
    Canyon:
    - Narrow DEM (spikes/henderson-canyon/, lon ~-116.43 to -116.32):
      produced truncated boundary.
    - Wide DEM (data/derived/watershed/dem_10m_wide.tif, to lon -116.50):
      captured the full 107 km² headwater with 93.5% HUC-12 overlap.

    The output is geometrically equivalent across reruns but not
    byte-identical. shapely unary_union and simplify go through
    floating-point operations where union ordering depends on polygon
    iteration order from features.shapes(), which is not guaranteed stable.
    """
    dem = Path(dem).resolve()
    pour_geometry_path = Path(pour_geometry_path).resolve()
    output_boundary = Path(output_boundary).resolve()
    output_boundary.parent.mkdir(parents=True, exist_ok=True)

    wbt = WhiteboxTools()
    work_dir = output_boundary.parent
    wbt.set_working_dir(str(work_dir))
    wbt.set_verbose_mode(False)

    # ── Load DEM metadata ──
    with rasterio.open(dem) as src:
        dem_crs = src.crs
        dem_transform = src.transform
        dem_shape = src.shape
        dem_res = abs(dem_transform.a)
        dem_bounds = src.bounds
        print(f"  DEM: {dem_shape[1]}×{dem_shape[0]}, CRS={dem_crs}, res={dem_res:.1f}m")

    # ── Load and reproject pour geometry ──
    pour_gdf = gpd.read_file(pour_geometry_path)
    if pour_gdf.crs != dem_crs:
        pour_gdf = pour_gdf.to_crs(dem_crs)
    pour_geom = pour_gdf.geometry.iloc[0]

    # Overlap check
    from shapely.geometry import box
    dem_box = box(*dem_bounds)
    if not pour_geom.intersects(dem_box):
        raise ValueError(
            f"Pour geometry from {pour_geometry_path} does not overlap DEM extent "
            f"({dem_bounds}). Check CRS alignment."
        )
    print(f"  Pour geometry: {pour_geom.geom_type}, overlaps DEM ✓")

    # ── Step 1: Rasterize pour points ──
    pour_raster = work_dir / "_watershed_pour.tif"
    pour_profile = {
        "driver": "GTiff",
        "count": 1,
        "height": dem_shape[0],
        "width": dem_shape[1],
        "transform": dem_transform,
        "crs": dem_crs,
        "dtype": "uint8",
        "compress": "lzw",
    }
    t0 = time.time()
    # int16 raster with uint8 mask — see LESSONS.md
    mask = features.rasterize(
        [(pour_geom, 1)],
        out_shape=dem_shape,
        transform=dem_transform,
        dtype="uint8",
    )
    with rasterio.open(pour_raster, "w", **pour_profile) as dst:
        dst.write(mask, 1)
    n_pour = int(mask.sum())
    print(f"  Pour raster: {n_pour:,} cells in {time.time()-t0:.1f}s")
    if n_pour == 0:
        raise ValueError(
            f"No pour cells rasterized from {pour_geometry_path}. "
            "Geometry may be outside the DEM extent or too small for the DEM resolution."
        )

    # ── Step 2: D8 pointer ──
    d8_ptr = work_dir / "_watershed_d8_ptr.tif"
    t0 = time.time()
    wbt.d8_pointer(str(dem), str(d8_ptr))
    if not d8_ptr.exists():
        raise RuntimeError("WBT d8_pointer failed")
    print(f"  D8 pointer: {time.time()-t0:.0f}s")

    # ── Step 2b: Snap pour points (optional) ──
    snap_raster = pour_raster
    if snap_distance_m is not None:
        # Compute D8 accumulation for stream identification
        d8_accum = work_dir / "_watershed_d8_accum.tif"
        wbt.d8_flow_accumulation(str(dem), str(d8_accum),
                                  out_type="cells", pntr=str(d8_ptr))
        if not d8_accum.exists():
            raise RuntimeError("WBT d8_flow_accumulation failed for snapping")

        streams = work_dir / "_watershed_snap_streams.tif"
        wbt.extract_streams(str(d8_accum), str(streams),
                             snap_stream_threshold, zero_background=True)

        snap_raster = work_dir / "_watershed_pour_snapped.tif"
        wbt.snap_pour_points(str(pour_raster), str(streams),
                              str(snap_raster), snap_distance_m)
        if not snap_raster.exists():
            raise RuntimeError("WBT snap_pour_points failed")

        with rasterio.open(snap_raster) as s:
            n_snapped = int((s.read(1) > 0).sum())
        print(f"  Snap ({snap_distance_m}m): {n_pour:,} → {n_snapped:,} cells")

        # Clean up accum + streams
        if not keep_intermediates:
            d8_accum.unlink()
            streams.unlink()

    # ── Step 3: WBT watershed ──
    watershed_rast = work_dir / "_watershed_mask.tif"
    t0 = time.time()
    wbt.watershed(str(d8_ptr), str(snap_raster), str(watershed_rast))
    if not watershed_rast.exists():
        raise RuntimeError("WBT watershed failed")

    with rasterio.open(watershed_rast) as src:
        ws_data = src.read(1)
        ws_res = abs(src.transform.a)
        ws_cells = int((ws_data > 0).sum())
    ws_area_km2 = ws_cells * ws_res * ws_res / 1e6
    print(f"  Watershed: {ws_cells:,} cells, {ws_area_km2:.1f} km² in {time.time()-t0:.0f}s")

    if ws_cells == 0:
        raise RuntimeError("Watershed delineation produced zero cells — check pour points")

    # ── Edge-touch check ──
    with rasterio.open(watershed_rast) as src:
        ws_rows, ws_cols = np.where(ws_data > 0)
    half_res = dem_res * 2  # 2-pixel threshold
    edge_warnings = []
    if ws_rows.min() < 2:
        edge_warnings.append(f"north margin within {half_res:.1f}m")
    if ws_rows.max() > dem_shape[0] - 3:
        edge_warnings.append(f"south margin within {half_res:.1f}m")
    if ws_cols.min() < 2:
        edge_warnings.append(f"west margin within {half_res:.1f}m")
    if ws_cols.max() > dem_shape[1] - 3:
        edge_warnings.append(f"east margin within {half_res:.1f}m")
    if edge_warnings:
        warnings.warn(
            "Watershed boundary touches DEM edge ("
            + ", ".join(edge_warnings)
            + "). The DEM extent may be too small to capture the full upstream "
            "contributing area. Verify with a wider DEM if the boundary shape "
            "suggests truncation."
        )

    # ── Step 4: Polygonize ──
    t0 = time.time()
    binary = (ws_data > 0).astype("int16")
    mask_uint8 = (ws_data > 0).astype("uint8")
    # int16 raster + uint8 mask — see LESSONS.md
    results = list(features.shapes(binary, mask=mask_uint8, transform=dem_transform))
    geoms = [shape(g) for g, v in results if v == 1]
    if not geoms:
        raise RuntimeError("Polygonization produced zero geometries")
    print(f"  Polygonized: {len(geoms)} fragments in {time.time()-t0:.1f}s")

    merged = unary_union(geoms)
    simplified = merged.simplify(10, preserve_topology=True)
    print(f"  Merged: {merged.geom_type}, area={merged.area/1e6:.1f} km²")
    if hasattr(simplified, "exterior"):
        print(f"  Simplified: {len(simplified.exterior.coords)} vertices")
    else:
        print(f"  Simplified: {simplified.geom_type}")

    # ── Step 5: Save ──
    gdf_5070 = gpd.GeoDataFrame(
        [{"name": "Watershed boundary",
          "area_km2": round(ws_area_km2, 2),
          "cells": int(ws_cells),
          "resolution_m": dem_res}],
        geometry=[simplified],
        crs=dem_crs,
    )

    gdf_4326 = gdf_5070.to_crs("EPSG:4326")
    gdf_4326.to_file(output_boundary, driver="GeoJSON")
    bnd_4326 = gdf_4326.total_bounds
    print(f"  WGS84: lon [{bnd_4326[0]:.4f}, {bnd_4326[2]:.4f}], "
          f"lat [{bnd_4326[1]:.4f}, {bnd_4326[3]:.4f}] → {output_boundary}")

    if output_boundary_5070:
        output_boundary_5070 = Path(output_boundary_5070).resolve()
        output_boundary_5070.parent.mkdir(parents=True, exist_ok=True)
        gdf_5070.to_file(output_boundary_5070, driver="GeoJSON")
        print(f"  EPSG:5070 → {output_boundary_5070}")

    # ── Cleanup ──
    if not keep_intermediates:
        for p in [d8_ptr, watershed_rast, pour_raster, snap_raster]:
            if p.exists() and p != pour_raster:  # always remove pour/snap rasters
                p.unlink()
        if pour_raster.exists():
            pour_raster.unlink()
        if snap_raster.exists() and snap_raster != pour_raster:
            snap_raster.unlink()

    return gdf_4326
