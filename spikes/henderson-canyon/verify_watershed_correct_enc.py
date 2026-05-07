"""Verify watershed with CORRECT D8 encoding.

Encoding bug history (2026-05-06):
  The original verification scripts (trace_western_flow.py, diagnose_d8_vs_dinf.py,
  verify_watershed_upstream.py) used a 45-degree-rotated D8 direction encoding:
    1=NE, 2=N, 4=NW, 8=W, 16=SW, 32=S, 64=SE, 128=E
  This mapping assigns cardinal directions (N/S/E/W) to the wrong offsets.
  The CORRECT WhiteboxTools D8 pointer encoding is:
    1=NE, 2=E, 4=SE, 8=S, 16=SW, 32=W, 64=NW, 128=N
  The bug caused downstream traces to follow incorrect paths, producing a false
  "96% of watershed is incorrect" finding in May 2026. The WBT watershed() output
  was correct all along; only the verification code was wrong.

  When writing any code that manually reads WBT D8 pointer rasters, use the
  encoding table below. Do NOT use the rotated variant found in older spike scripts.

  WBT D8 pointer encoding:
    1=NE, 2=E, 4=SE, 8=S, 16=SW, 32=W, 64=NW, 128=N
    dr: {1:-1, 2:0, 4:1, 8:1, 16:1, 32:0, 64:-1, 128:-1}
    dc: {1:1,  2:1, 4:1, 8:0, 16:-1, 32:-1, 64:-1, 128:0}
"""
import numpy as np
from pathlib import Path
import rasterio
import geopandas as gpd
from shapely.geometry import Point
from collections import deque

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
SPIKE = ROOT / "spikes" / "henderson-canyon"

with rasterio.open(SPIKE / "watershed.tif") as src:
    ws_mask = src.read(1)
    ws_crs = src.crs
    ws_tr = src.transform

with rasterio.open(SPIKE / "d8_pointer.tif") as src:
    d8 = src.read(1)

# CORRECT WBT encoding: 1=NE, 2=E, 4=SE, 8=S, 16=SW, 32=W, 64=NW, 128=N
d8_dr = {1:-1, 2:0, 4:1, 8:1, 16:1, 32:0, 64:-1, 128:-1}
d8_dc = {1:1,  2:1, 4:1, 8:0, 16:-1,32:-1,64:-1,128:0}

# Upstream mapping: for each neighbor (dr,dc), which D8 values mean "flows to center"?
neighbor_offsets = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
upstream_map = {}
for dr, dc in neighbor_offsets:
    matching = []
    for d, ddr in d8_dr.items():
        ddc = d8_dc[d]
        if ddr == -dr and ddc == -dc:
            matching.append(d)
    upstream_map[(dr, dc)] = matching

# Community bbox pour cells
comm = gpd.read_file(ROOT / "outputs/maps/deanza_community_poi.geojson")
comm_5070 = comm.to_crs(ws_crs)
from rasterio import features
comm_rast = features.rasterize(
    [(comm_5070.geometry.iloc[0], 1)],
    out_shape=ws_mask.shape, transform=ws_tr, dtype='uint8'
)
pour = np.where(comm_rast > 0)

# BFS upstream
visited = np.zeros(ws_mask.shape, dtype=bool)
queue = deque()
for r, c in zip(*pour):
    if 0 <= r < d8.shape[0] and 0 <= c < d8.shape[1]:
        visited[r, c] = True
        queue.append((r, c))

while queue:
    r, c = queue.popleft()
    for (dr, dc), codes in upstream_map.items():
        nr, nc = r + dr, c + dc
        if nr < 0 or nr >= d8.shape[0] or nc < 0 or nc >= d8.shape[1]:
            continue
        if visited[nr, nc]:
            continue
        if d8[nr, nc] in codes:
            visited[nr, nc] = True
            queue.append((nr, nc))

bfs_cells = visited.sum()
ws_cells = (ws_mask > 0).sum()
agreement = (visited & (ws_mask > 0)).sum()
bfs_only = (visited & ~(ws_mask > 0)).sum()
ws_only = (~visited & (ws_mask > 0)).sum()

print(f"BFS upstream (correct encoding): {bfs_cells:,} cells")
print(f"WBT watershed() result:          {ws_cells:,} cells")
print(f"Agreement:                       {agreement:,}")
print(f"BFS only (WBT missed):           {bfs_only:,}")
print(f"WBT only (false positives):      {ws_only:,}")

# Test disputed cells
if ws_only > 0:
    d_rows, d_cols = np.where(~visited & (ws_mask > 0))
    print(f"\nSpot-checking {min(10, len(d_rows))} WBT-only cells:")
    hit = 0
    for i in range(min(10, len(d_rows))):
        r, c = d_rows[i], d_cols[i]
        # Trace downstream
        path_len = 0
        cr, cc = r, c
        for _ in range(10000):
            val = d8[cr, cc]
            if val not in d8_dr:
                break
            cr += d8_dr[val]
            cc += d8_dc[val]
            path_len += 1
            if cr < 0 or cr >= d8.shape[0] or cc < 0 or cc >= d8.shape[1]:
                break
            x = ws_tr.c + (cc + 0.5) * ws_tr.a
            y = ws_tr.f + (cr + 0.5) * ws_tr.e
            if comm_5070.contains(Point(x, y)).any():
                hit += 1
                break
        sx = ws_tr.c + (c + 0.5) * ws_tr.a
        sy = ws_tr.f + (r + 0.5) * ws_tr.e
        print(f"  ({sx:.0f},{sy:.0f}) {path_len} steps -> {'HIT' if hit > 0 and i < hit else 'miss'}")
    
    # More thorough: sample 100
    import random
    random.seed(42)
    sample_idx = random.sample(range(len(d_rows)), min(100, len(d_rows)))
    hit_count = 0
    for idx in sample_idx:
        r, c = d_rows[idx], d_cols[idx]
        cr, cc = r, c
        for _ in range(10000):
            val = d8[cr, cc]
            if val not in d8_dr:
                break
            cr += d8_dr[val]
            cc += d8_dc[val]
            if cr < 0 or cr >= d8.shape[0] or cc < 0 or cc >= d8.shape[1]:
                break
            x = ws_tr.c + (cc + 0.5) * ws_tr.a
            y = ws_tr.f + (cr + 0.5) * ws_tr.e
            if comm_5070.contains(Point(x, y)).any():
                hit_count += 1
                break
    print(f"\n  {hit_count}/{len(sample_idx)} sampled WBT-only cells reach community")

# Compute area of BFS result
bfs_rows, bfs_cols = np.where(visited)
area = len(bfs_rows) * abs(ws_tr.a * ws_tr.e) / 1e6
bfs_x = ws_tr.c + (bfs_cols + 0.5) * ws_tr.a
print(f"\nBFS watershed area: {area:.1f} km²")
print(f"E-W extent: {(bfs_x.max()-bfs_x.min())/1000:.1f} km")
