from __future__ import annotations

import time
from collections import deque
from pathlib import Path

import numpy as np
import rasterio
from rasterio import features
from shapely.geometry import shape
from shapely.ops import unary_union
import geopandas as gpd


# D∞ neighbor lookup: index → (row_delta, col_delta)
# 0=E, 1=NE, 2=N, 3=NW, 4=W, 5=SW, 6=S, 7=SE
_DINF_NEIGHBORS = [
    (0, 1), (-1, 1), (-1, 0), (-1, -1),
    (0, -1), (1, -1), (1, 0), (1, 1),
]


def _neighbors_flowing_into(r, c, ptr, rows, cols):
    """Return (nr, nc) cells whose D∞ angle points toward (r, c).

    WBT D∞ pointer encoding: degrees, 0=east, counter-clockwise.
    A cell at neighbor direction out_idx from (r,c) flows into (r,c)
    when its angle includes the reverse direction (out_idx+4)%8.
    """
    result = []
    for out_idx, (dr, dc) in enumerate(_DINF_NEIGHBORS):
        nr, nc = r + dr, c + dc
        if nr < 0 or nr >= rows or nc < 0 or nc >= cols:
            continue
        angle = float(ptr[nr, nc])
        if angle < 0 or angle >= 360:
            continue
        angle %= 360
        rev_dir = (out_idx + 4) % 8
        idx1 = int(angle // 45) % 8
        frac = (angle - idx1 * 45) / 45.0
        if ((idx1 == rev_dir and frac < 1 - 1e-6) or
                ((idx1 + 1) % 8 == rev_dir and frac > 1e-6)):
            result.append((nr, nc))
    return result


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

    tgdf = target_gdf.to_crs(p_crs)
    target_geom = unary_union(tgdf.geometry.values)
    target_mask = features.rasterize(
        [(target_geom, 1)],
        out_shape=p_shape, transform=p_transform, dtype="uint8",
    )
    n_target = int(target_mask.sum())
    if n_target == 0:
        raise ValueError("Target geometry rasterized to 0 cells — check CRS")

    print(f"  Target: {n_target:,} cells")

    visited = np.zeros(p_shape, dtype="uint8")
    queue = deque()
    for r, c in zip(*np.where(target_mask > 0)):
        visited[int(r), int(c)] = 1
        queue.append((int(r), int(c)))

    print(f"  Tracing upstream from {len(queue):,} seed cells…")
    t0 = time.time()
    while queue:
        r, c = queue.popleft()
        for nr, nc in _neighbors_flowing_into(r, c, ptr, rows, cols):
            if not visited[nr, nc]:
                visited[nr, nc] = 1
                queue.append((nr, nc))

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
