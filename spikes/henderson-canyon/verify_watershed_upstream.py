"""Trace UPSTREAM from community bbox pour points to find actual contributing area."""
import numpy as np
from pathlib import Path
import rasterio
import geopandas as gpd
from collections import deque

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
SPIKE = ROOT / "spikes" / "henderson-canyon"

with rasterio.open(SPIKE / "watershed.tif") as src:
    ws_mask = src.read(1)
    ws_crs = src.crs
    ws_transform = src.transform

with rasterio.open(SPIKE / "d8_pointer.tif") as src:
    d8_ptr = src.read(1)

# D8 reverse lookup: for each direction, what neighbor cell would point to center?
# To go upstream FROM a cell, we need to find neighbors whose D8 pointer
# points INTO this cell. Example:
# NW neighbor at (r-1,c-1): to flow SE into (r,c), it must have D8=4 (SE). 
# CORRECT WBT D8 encoding: 1=NE, 2=E, 4=SE, 8=S, 16=SW, 32=W, 64=NW, 128=N
d8_to_dr = {1:-1, 2:0, 4:1, 8:1, 16:1, 32:0, 64:-1, 128:-1}
d8_to_dc = {1:1, 2:1, 4:1, 8:0, 16:-1, 32:-1, 64:-1, 128:0}

# For each neighbor offset, what D8 value means "flows to center"?
# Neighbor at (r+dr, c+dc) has D8=d means it flows to (r+dr+dr_d8[d], c+dc+dc_d8[d])
# We want: r+dr+dr_d8[d] == r and c+dc+dc_d8[d] == c
# So: dr_d8[d] == -dr and dc_d8[d] == -dc
# Precompute: for each neighbor offset, find matching D8 values
upstream_map = {}  # (dr, dc) -> list of D8 values that flow to center
neighbor_offsets = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
for dr, dc in neighbor_offsets:
    matching = []
    for d, ddr in d8_to_dr.items():
        ddc = d8_to_dc[d]
        if ddr == -dr and ddc == -dc:
            matching.append(d)
    upstream_map[(dr, dc)] = matching

# Community bbox pour points: rasterize the polygon
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
print(f"Community bbox pour cells: {len(pour_cells[0]):,}")

# BFS upstream from all pour cells
visited = np.zeros(ws_mask.shape, dtype=bool)
queue = deque()

for r, c in zip(*pour_cells):
    if 0 <= r < d8_ptr.shape[0] and 0 <= c < d8_ptr.shape[1]:
        visited[r, c] = True
        queue.append((r, c))

iteration = 0
while queue:
    r, c = queue.popleft()
    iteration += 1
    # Check all 8 neighbors
    for (dr, dc), d8_vals in upstream_map.items():
        nr, nc = r + dr, c + dc
        if nr < 0 or nr >= d8_ptr.shape[0] or nc < 0 or nc >= d8_ptr.shape[1]:
            continue
        if visited[nr, nc]:
            continue
        # Does this neighbor flow INTO (r,c)?
        if d8_ptr[nr, nc] in d8_vals:
            visited[nr, nc] = True
            queue.append((nr, nc))

actual_cells = visited.sum()
ws_cells = (ws_mask > 0).sum()
print(f"\nActual upstream cells (BFS): {actual_cells:,}")
print(f"Watershed tool result:        {ws_cells:,}")
print(f"Difference:                   {actual_cells - ws_cells:,}")
print(f"Ratio:                        {actual_cells/ws_cells:.1%}")

# Find actual western extent
actual_rows, actual_cols = np.where(visited)
if len(actual_rows) > 0:
    actual_x = ws_transform.c + (actual_cols + 0.5) * ws_transform.a
    actual_y = ws_transform.f + (actual_rows + 0.5) * ws_transform.e
    print(f"\nActual contributing area:")
    print(f"  Extent X: {actual_x.min():.0f} to {actual_x.max():.0f} ({(actual_x.max()-actual_x.min())/1000:.1f} km)")
    print(f"  Extent Y: {actual_y.min():.0f} to {actual_y.max():.0f} ({(actual_y.max()-actual_y.min())/1000:.1f} km)")
    print(f"  Cell area: {len(actual_rows) * (ws_transform.a * abs(ws_transform.e)) / 1e6:.1f} km²")
    
    # Compare to watershed tool
    ws_rows, ws_cols = np.where(ws_mask > 0)
    ws_xx = ws_transform.c + (ws_cols + 0.5) * ws_transform.a
    print(f"\nWatershed tool result:")
    print(f"  Extent X: {ws_xx.min():.0f} to {ws_xx.max():.0f} ({(ws_xx.max()-ws_xx.min())/1000:.1f} km)")
    print(f"  Extra west: {(ws_xx.min() - actual_x.min())/1000:.1f} km")
    
    # Reproject to WGS84
    from rasterio.warp import transform
    actual_lon_min, _ = transform(ws_crs, "EPSG:4326", [actual_x.min()], [0])
    actual_lon_max, _ = transform(ws_crs, "EPSG:4326", [actual_x.max()], [0])
    ws_lon_min, _ = transform(ws_crs, "EPSG:4326", [ws_xx.min()], [0])
    print(f"\n  WGS84 extent - actual:     {actual_lon_min[0]:.4f} to {actual_lon_max[0]:.4f}")
    print(f"  WGS84 extent - watershed:  {ws_lon_min[0]:.4f} (extra {(actual_lon_min[0]-ws_lon_min[0])*111.32*0.85:.1f} km)")

# Save the actual contributing area as a binary raster for visualization
actual_path = SPIKE / "actual_watershed_bfs.tif"
profile = src.profile.copy()
profile.update(dtype='uint8', compress='lzw')
actual_mask = visited.astype('uint8')
with rasterio.open(actual_path, 'w', **profile) as dst:
    dst.write(actual_mask, 1)
print(f"\nSaved actual watershed: {actual_path}")
