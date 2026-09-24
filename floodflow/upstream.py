from __future__ import annotations

import time
from pathlib import Path

import geopandas as gpd
import numba
import numpy as np
import rasterio
from rasterio import features
from shapely.geometry import shape
from shapely.ops import unary_union

from floodflow.encoding import DINF_NEIGHBORS
from floodflow.geo import polygon_mask

# WBT D∞ pointer: degrees, 0=North, clockwise.
_DR = np.array([d[0] for d in DINF_NEIGHBORS], dtype=np.int64)
_DC = np.array([d[1] for d in DINF_NEIGHBORS], dtype=np.int64)


@numba.njit(cache=True)
def _flows_toward(angle: float, direction: int) -> bool:
    """Does a cell with D∞ `angle` send any flow in `direction` (0=N … 7=NW)?

    Single source of truth for the trace. Flats/nodata (angle outside
    [0, 360], or NaN) send nothing; 360° wraps to North."""
    if not (angle >= 0.0 and angle <= 360.0):
        return False
    angle = angle % 360.0
    idx1 = int(angle // 45.0) % 8
    frac = (angle - idx1 * 45.0) / 45.0
    return ((idx1 == direction and frac < 1.0 - 1e-6) or
            ((idx1 + 1) % 8 == direction and frac > 1e-6))


def _neighbors_flowing_into(r, c, ptr, rows, cols):
    """Return (nr, nc) cells whose D∞ angle points toward (r, c).

    A neighbor at direction out_idx from (r, c) flows into (r, c) when
    its angle spans the reverse direction (out_idx + 4) % 8.
    """
    result = []
    for out_idx, (dr, dc) in enumerate(DINF_NEIGHBORS):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols and \
                _flows_toward(float(ptr[nr, nc]), (out_idx + 4) % 8):
            result.append((nr, nc))
    return result


@numba.njit(cache=True)
def _trace_upstream(ptr: np.ndarray, target: np.ndarray) -> np.ndarray:
    """BFS from every target cell to all cells with any D∞ flow into the
    visited set. Returns a uint8 mask. Each cell is queued at most once, so
    the queue is a flat array of packed row*cols+col indices."""
    rows, cols = ptr.shape
    visited = np.zeros((rows, cols), dtype=np.uint8)
    queue = np.empty(rows * cols, dtype=np.int64)
    head = tail = 0
    for r in range(rows):
        for c in range(cols):
            if target[r, c]:
                visited[r, c] = 1
                queue[tail] = r * cols + c
                tail += 1
    while head < tail:
        idx = queue[head]
        head += 1
        r, c = idx // cols, idx % cols
        for k in range(8):
            nr, nc = r + _DR[k], c + _DC[k]
            if nr < 0 or nr >= rows or nc < 0 or nc >= cols or visited[nr, nc]:
                continue
            if _flows_toward(np.float64(ptr[nr, nc]), (k + 4) % 8):
                visited[nr, nc] = 1
                queue[tail] = nr * cols + nc
                tail += 1
    return visited


def contributing_area(
    pointer: Path,
    target_gdf: gpd.GeoDataFrame,
    output_mask: Path | None = None,
    output_boundary: Path | None = None,
    *,
    simplify_m: float = 10.0,
) -> gpd.GeoDataFrame:
    """D∞ upstream contributing area to a target polygon.

    Raises RuntimeError if the BFS reaches the pointer boundary — the DEM
    extent was too small to capture the full upstream area.

    Returns a WGS84 GeoDataFrame with properties: area_km2, cells,
    resolution_m, trace_type.
    """
    pointer = Path(pointer)

    with rasterio.open(pointer) as src:
        ptr = src.read(1)
        p_crs = src.crs
        p_transform = src.transform
        p_shape = src.shape
        p_res = abs(p_transform.a)

    rows, cols = p_shape

    target_mask = polygon_mask(target_gdf, p_crs, p_transform, p_shape)
    n_target = int(target_mask.sum())
    if n_target == 0:
        raise ValueError("Target geometry rasterized to 0 cells — check CRS")

    print(f"  Target: {n_target:,} cells")

    print(f"  Tracing upstream from {n_target:,} seed cells…")
    t0 = time.time()
    visited = _trace_upstream(ptr, target_mask)

    n_contrib = int(visited.sum())
    area_km2 = n_contrib * p_res * p_res / 1e6
    print(f"  Contributing area: {n_contrib:,} cells, {area_km2:.1f} km² "
          f"in {time.time() - t0:.0f}s")

    cr, cc = np.where(visited > 0)
    if (cr.min() < 2 or cr.max() > rows - 3 or
            cc.min() < 2 or cc.max() > cols - 3):
        raise RuntimeError(
            f"Contributing area BFS reached the pointer boundary "
            f"(visited rows {cr.min()}–{cr.max()} of {rows}, "
            f"cols {cc.min()}–{cc.max()} of {cols}). "
            f"The DEM extent is too small to capture the full upstream area. "
            f"Increase bootstrap buffer_m and re-run."
        )

    if output_mask:
        output_mask = Path(output_mask)
        output_mask.parent.mkdir(parents=True, exist_ok=True)
        prof = {"driver": "GTiff", "count": 1, "height": rows, "width": cols,
                "transform": p_transform, "crs": p_crs, "dtype": "uint8",
                "compress": "lzw"}
        with rasterio.open(output_mask, "w", **prof) as dst:
            dst.write(visited, 1)
        print(f"  Mask → {output_mask}")

    geoms = [shape(g) for g, v in
             features.shapes(visited.astype("int16"), mask=visited,
                             transform=p_transform)
             if v == 1]
    if not geoms:
        raise RuntimeError("Polygonization produced zero geometries")
    simplified = unary_union(geoms).simplify(simplify_m, preserve_topology=True)
    print(f"  Polygonized: {len(geoms)} fragments → {simplified.geom_type}")

    gdf_proj = gpd.GeoDataFrame(
        [{"area_km2": round(area_km2, 2), "cells": int(n_contrib),
          "resolution_m": p_res, "trace_type": "boolean_dinf"}],
        geometry=[simplified], crs=p_crs,
    )

    if output_boundary:
        output_boundary = Path(output_boundary)
        output_boundary.parent.mkdir(parents=True, exist_ok=True)
        gdf_proj.to_file(output_boundary, driver="GeoJSON")
        print(f"  Boundary → {output_boundary}")

    return gdf_proj.to_crs("EPSG:4326")
