"""Complete watershed verification: BFS upstream trace + save + dispute check."""
import numpy as np
from pathlib import Path
import rasterio
import geopandas as gpd
from shapely.geometry import Point
from collections import deque

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
SPIKE = ROOT / "spikes" / "henderson-canyon"

# Load all rasters first
with rasterio.open(SPIKE / "watershed.tif") as src:
    ws_mask = src.read(1)
    ws_crs = src.crs
    ws_transform = src.transform
    ws_profile = src.profile

with rasterio.open(SPIKE / "d8_pointer.tif") as src:
    d8_ptr = src.read(1)

# D8 encoding
d8_dr = {1:-1, 2:-1, 4:-1, 8:0, 16:1, 32:1, 64:1, 128:0}
d8_dc = {1:1, 2:0, 4:-1, 8:-1, 16:-1, 32:0, 64:1, 128:1}

# Upstream mapping: for each neighbor offset, which D8 values mean "flows to center"?
neighbor_offsets = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
upstream_map = {}
for dr, dc in neighbor_offsets:
    matching = []
    for d, ddr in d8_dr.items():
        ddc = d8_dc[d]
        if ddr == -dr and ddc == -dc:
            matching.append(d)
    upstream_map[(dr, dc)] = matching

# Rasterize community bbox
comm = gpd.read_file(ROOT / "outputs/maps/deanza_community_poi.geojson")
comm_5070 = comm.to_crs(ws_crs)
from rasterio import features
comm_rast = features.rasterize(
    [(comm_5070.geometry.iloc[0], 1)],
    out_shape=ws_mask.shape,
    transform=ws_transform,
    dtype='uint8'
)
pour_cells = np.where(comm_rast > 0)
print(f"Community pour cells: {len(pour_cells[0]):,}")

# BFS upstream
visited = np.zeros(ws_mask.shape, dtype=bool)
queue = deque()
for r, c in zip(*pour_cells):
    if 0 <= r < d8_ptr.shape[0] and 0 <= c < d8_ptr.shape[1]:
        visited[r, c] = True
        queue.append((r, c))

while queue:
    r, c = queue.popleft()
    for (dr, dc), d8_vals in upstream_map.items():
        nr, nc = r + dr, c + dc
        if nr < 0 or nr >= d8_ptr.shape[0] or nc < 0 or nc >= d8_ptr.shape[1]:
            continue
        if visited[nr, nc]:
            continue
        if d8_ptr[nr, nc] in d8_vals:
            visited[nr, nc] = True
            queue.append((nr, nc))

bfs_cells = visited.sum()
ws_cells = (ws_mask > 0).sum()
print(f"BFS upstream cells: {bfs_cells:,}")
print(f"WBT watershed cells: {ws_cells:,}")
print(f"Ratio: {bfs_cells/ws_cells:.1%}")

# Save BFS mask
bfs_path = SPIKE / "actual_watershed_bfs.tif"
ws_profile.update(dtype='uint8', compress='lzw', nodata=0)
with rasterio.open(bfs_path, 'w', **ws_profile) as dst:
    dst.write(visited.astype('uint8'), 1)
print(f"Saved BFS mask: {bfs_path}")

# Now spot-check disputed cells
disputed = (ws_mask > 0) & ~visited
agreement = (ws_mask > 0) & visited
print(f"\nDisputed cells (WBT only): {disputed.sum():,}")
print(f"Agreement: {agreement.sum():,}")

if disputed.sum() == 0:
    print("No disputed cells — WBT and BFS agree.")
    exit()

d_rows, d_cols = np.where(disputed)
d_x = ws_transform.c + (d_cols + 0.5) * ws_transform.a
d_y = ws_transform.f + (d_rows + 0.5) * ws_transform.e

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

comm_polygon = comm_5070.geometry.iloc[0]

# Test cells at various distances from community
for label, frac in [("edge of community", 0.01), ("near west (1km)", 0.1),
                      ("mid west (3km)", 0.3), ("far west (6km)", 0.6),
                      ("extreme west", 0.95)]:
    idx = int(len(d_x) * frac)
    idx = min(idx, len(d_x) - 1)
    r, c = d_rows[idx], d_cols[idx]
    sx = ws_transform.c + (c + 0.5) * ws_transform.a
    sy = ws_transform.f + (r + 0.5) * ws_transform.e
    end, reason, steps = trace_flow(r, c)
    
    in_comm = False
    end_desc = "unknown"
    if end is not None:
        ex = ws_transform.c + (end[1] + 0.5) * ws_transform.a
        ey = ws_transform.f + (end[0] + 0.5) * ws_transform.e
        in_comm = comm_polygon.contains(Point(ex, ey))
        end_desc = f"({ex:.0f},{ey:.0f})"
    
    dist_from_comm = ((sx - comm_5070.centroid.x.iloc[0])**2 + (sy - comm_5070.centroid.y.iloc[0])**2)**0.5
    print(f"  {label}: ({sx:.0f},{sy:.0f}) {dist_from_comm/1000:.1f}km from comm → {reason} after {steps} steps, ends at {end_desc}, in_comm={in_comm}")

# Summary: how many disputed cells actually reach community?
print("\nComputing full statistics on disputed cells...")
sample_n = min(1000, len(d_rows))
sample_idx = np.random.choice(len(d_rows), sample_n, replace=False)
hit = 0
for i in sample_idx:
    r, c = d_rows[i], d_cols[i]
    end, reason, steps = trace_flow(r, c)
    if end is not None:
        ex = ws_transform.c + (end[1] + 0.5) * ws_transform.a
        ey = ws_transform.f + (end[0] + 0.5) * ws_transform.e
        if comm_polygon.contains(Point(ex, ey)):
            hit += 1
print(f"  {hit}/{sample_n} ({100*hit/sample_n:.1f}%) disputed cells reach community")
