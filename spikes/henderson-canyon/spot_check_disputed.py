"""Spot-check: trace downstream from cells in the watershed tool's result but outside BFS result."""
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

# Load BFS result (if it was saved despite the error)
# If not, let me recompute a quick one
if bfs_mask.sum() == 0:
    print("BFS mask empty or not saved, recomputing...")
    bfs_mask = np.zeros(ws_mask.shape, dtype=bool)
else:
    print(f"BFS mask: {bfs_mask.sum():,} cells")

# Cells in WBT watershed but NOT in BFS trace
ws_only = ws_mask > 0
bfs_only = bfs_mask
disputed = ws_only & ~bfs_only
agreement = ws_only & bfs_only

print(f"WBT watershed cells: {ws_only.sum():,}")
print(f"BFS trace cells:     {bfs_only.sum():,}")
print(f"Disputed (WBT only): {disputed.sum():,}")
print(f"Agreement:           {agreement.sum():,}")

if disputed.sum() == 0:
    print("No disputed cells. They agree!")
    exit()

# Pick sample disputed cells spread across the area
d_rows, d_cols = np.where(disputed)
d_x = ws_transform.c + (d_cols + 0.5) * ws_transform.a
d_y = ws_transform.f + (d_rows + 0.5) * ws_transform.e

# Load D8 pointer
with rasterio.open(SPIKE / "d8_pointer.tif") as src:
    d8_ptr = src.read(1)

d8_dr = {1:-1, 2:-1, 4:-1, 8:0, 16:1, 32:1, 64:1, 128:0}
d8_dc = {1:1, 2:0, 4:-1, 8:-1, 16:-1, 32:0, 64:1, 128:1}

def trace_flow(r, c, max_steps=20000):
    for i in range(max_steps):
        if r < 0 or r >= d8_ptr.shape[0] or c < 0 or c >= d8_ptr.shape[1]:
            return None, "exited_raster", i
        direction = d8_ptr[r, c]
        if direction <= 0 or direction > 128 or (direction & (direction - 1)) != 0:
            return (r, c), "pit", i
        r += d8_dr[direction]
        c += d8_dc[direction]
    return (r, c), "max_steps", max_steps

# Community polygon
comm = gpd.read_file(ROOT / "outputs/maps/deanza_community_poi.geojson")
comm_5070 = comm.to_crs(ws_crs)
comm_polygon = comm_5070.geometry.iloc[0]

# Pick 10 disputed cells at various X positions
x_sorted = np.argsort(d_x)
sample_idx = [0, len(d_x)//8, len(d_x)//4, len(d_x)//2, 3*len(d_x)//4, len(d_x)-1]
# Also pick cells from near the western edge, middle, and eastern
for label, indices in [("westernmost", range(0, min(10, len(d_x)))),
                         ("mid-west", range(len(d_x)//4, len(d_x)//4+10)),
                         ("central", range(len(d_x)//2, len(d_x)//2+10))]:
    hit_comm = 0
    hit_elsewhere = 0
    for idx in indices:
        if idx >= len(d_x):
            break
        r, c = d_rows[idx], d_cols[idx]
        start_x = ws_transform.c + (c + 0.5) * ws_transform.a
        start_y = ws_transform.f + (r + 0.5) * ws_transform.e
        end, reason, steps = trace_flow(r, c)
        
        in_comm = False
        if end is not None:
            end_x = ws_transform.c + (end[1] + 0.5) * ws_transform.a
            end_y = ws_transform.f + (end[0] + 0.5) * ws_transform.e
            in_comm = comm_polygon.contains(Point(end_x, end_y))
        
        if in_comm:
            hit_comm += 1
        else:
            hit_elsewhere += 1
        
        if hit_comm + hit_elsewhere <= 5:  # print first few
            print(f"  Disputed ({start_x:.0f},{start_y:.0f}) -> {reason} after {steps} steps, in_comm={in_comm}")
    
    print(f"  [{label}] {hit_comm}/{hit_comm+hit_elsewhere} reach community")
