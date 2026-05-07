"""Final verification: test BFS-only and WBT-agreement cells to confirm BFS is correct."""
import numpy as np
from pathlib import Path
import rasterio
import geopandas as gpd
from shapely.geometry import Point

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
SPIKE = ROOT / "spikes" / "henderson-canyon"

with rasterio.open(SPIKE / "watershed.tif") as src:
    ws_mask = src.read(1)
    ws_crs = src.crs
    ws_transform = src.transform

with rasterio.open(SPIKE / "actual_watershed_bfs.tif") as src:
    bfs_mask = src.read(1) > 0

with rasterio.open(SPIKE / "d8_pointer.tif") as src:
    d8_ptr = src.read(1)

d8_dr = {1:-1, 2:-1, 4:-1, 8:0, 16:1, 32:1, 64:1, 128:0}
d8_dc = {1:1, 2:0, 4:-1, 8:-1, 16:-1, 32:0, 64:1, 128:1}

def trace_flow(r, c, max_steps=20000):
    for i in range(max_steps):
        if r < 0 or r >= d8_ptr.shape[0] or c < 0 or c >= d8_ptr.shape[1]:
            return None, "exited", i
        direction = d8_ptr[r, c]
        if direction <= 0 or direction > 128 or (direction & (direction - 1)) != 0:
            return (r, c), "pit", i
        r += d8_dr[direction]
        c += d8_dc[direction]
    return (r, c), "max_steps", max_steps

comm = gpd.read_file(ROOT / "outputs/maps/deanza_community_poi.geojson")
comm_5070 = comm.to_crs(ws_crs)
comm_polygon = comm_5070.geometry.iloc[0]

def check_set(label, mask, n=100):
    rows, cols = np.where(mask)
    if len(rows) == 0:
        print(f"  {label}: empty set")
        return
    n = min(n, len(rows))
    idx = np.random.choice(len(rows), n, replace=False)
    hit = 0
    for i in idx:
        r, c = rows[i], cols[i]
        end, reason, steps = trace_flow(r, c)
        if end is not None:
            ex = ws_transform.c + (end[1] + 0.5) * ws_transform.a
            ey = ws_transform.f + (end[0] + 0.5) * ws_transform.e
            if comm_polygon.contains(Point(ex, ey)):
                hit += 1
    print(f"  {label}: {hit}/{n} ({100*hit/n:.0f}%) reach community")

# Test three sets
wbt = ws_mask > 0
bfs = bfs_mask

# Agreement (both say yes)
agreement = wbt & bfs
print(f"Agreement cells: {agreement.sum():,}")
check_set("Agreement (both)", agreement)

# BFS only (BFS found, WBT missed)
bfs_only = bfs & ~wbt
print(f"BFS-only cells: {bfs_only.sum():,}")
check_set("BFS only", bfs_only)

# WBT only (WBT found, BFS says no) - already tested 0/1000
wbt_only = wbt & ~bfs
print(f"WBT-only cells: {wbt_only.sum():,}")

# Also: test cells just outside both (should NOT reach community)
neither = (~wbt) & (~bfs)
n_rows, n_cols = np.where(neither)
if len(n_rows) > 0:
    n_test = min(100, len(n_rows))
    idx = np.random.choice(len(n_rows), n_test, replace=False)
    hit = 0
    for i in idx:
        r, c = n_rows[i], n_cols[i]
        end, reason, steps = trace_flow(r, c)
        if end is not None:
            ex = ws_transform.c + (end[1] + 0.5) * ws_transform.a
            ey = ws_transform.f + (end[0] + 0.5) * ws_transform.e
            if comm_polygon.contains(Point(ex, ey)):
                hit += 1
    print(f"  Neither (control): {hit}/{n_test} ({100*hit/n_test:.0f}%) reach community")

# Compute actual watershed extent
bfs_rows, bfs_cols = np.where(bfs)
bfs_x = ws_transform.c + (bfs_cols + 0.5) * ws_transform.a
bfs_y = ws_transform.f + (bfs_rows + 0.5) * ws_transform.e

from rasterio.warp import transform
lon_min, _ = transform(ws_crs, "EPSG:4326", [bfs_x.min()], [0])
lon_max, _ = transform(ws_crs, "EPSG:4326", [bfs_x.max()], [0])
lat_min, _ = transform(ws_crs, "EPSG:4326", [0], [bfs_y.min()])
lat_max, _ = transform(ws_crs, "EPSG:4326", [0], [bfs_y.max()])

print(f"\nCorrect watershed extent:")
print(f"  Area: {len(bfs_rows) * abs(ws_transform.a * ws_transform.e) / 1e6:.1f} km²")
print(f"  WGS84: lon [{lon_min[0]:.4f}, {lon_max[0]:.4f}], lat [{lat_min[0]:.4f}, {lat_max[0]:.4f}]")
print(f"  E-W extent: {(bfs_x.max()-bfs_x.min())/1000:.1f} km")
print(f"  N-S extent: {(bfs_y.max()-bfs_y.min())/1000:.1f} km")
