"""Trace D8 flow from cells at various distances from western watershed edge."""
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
    dem_bounds = src.bounds

with rasterio.open(SPIKE / "d8_pointer.tif") as src:
    d8_ptr = src.read(1)
    d8_transform = src.transform

# D8 direction encoding (WBT standard)
d8_dr = {1:-1, 2:-1, 4:-1, 8:0,  16:1, 32:1, 64:1,  128:0}
d8_dc = {1:1,  2:0,  4:-1, 8:-1, 16:-1,32:0,64:1,  128:1}

def trace_flow(r, c, max_steps=20000):
    for _ in range(max_steps):
        if r < 0 or r >= d8_ptr.shape[0] or c < 0 or c >= d8_ptr.shape[1]:
            return None, "exited_raster"
        direction = d8_ptr[r, c]
        if direction <= 0 or direction > 128 or (direction & (direction - 1)) != 0:
            return (r, c), "pit_or_invalid"
        r += d8_dr[direction]
        c += d8_cd[direction] if 'd8_cd' in dir() else 0
    return (r, c), "max_steps"

# Fix: d8_cd wasn't defined properly
d8_cd = {1:1, 2:0, 4:-1, 8:-1, 16:-1, 32:0, 64:1, 128:1}

# Re-define with corrected dict
def trace_flow(r, c, max_steps=20000):
    path = [(r, c)]
    for _ in range(max_steps):
        if r < 0 or r >= d8_ptr.shape[0] or c < 0 or c >= d8_ptr.shape[1]:
            return path, "exited_raster"
        direction = d8_ptr[r, c]
        if direction <= 0 or direction > 128 or (direction & (direction - 1)) != 0:
            return path, "pit"
        dr = {1:-1, 2:-1, 4:-1, 8:0, 16:1, 32:1, 64:1, 128:0}[direction]
        dc = {1:1, 2:0, 4:-1, 8:-1, 16:-1, 32:0, 64:1, 128:1}[direction]
        r += dr
        c += dc
        path.append((r, c))
    return path, "max_steps"

# Community & parcel polygons
comm = gpd.read_file(ROOT / "outputs/maps/deanza_community_poi.geojson")
comm_5070 = comm.to_crs(ws_crs)
comm_polygon = comm_5070.geometry.iloc[0]

parcel = gpd.read_file(ROOT / "data/vectors/deanza_villas_complex_boundary.geojson")
parcel_5070 = parcel.to_crs(ws_crs)
parcel_polygon = parcel_5070.geometry.iloc[0]

# Find watershed cells at various X offsets from western edge
ws_rows, ws_cols = np.where(ws_mask > 0)
ws_x = ws_transform.c + (ws_cols + 0.5) * ws_transform.a
ws_y = ws_transform.f + (ws_rows + 0.5) * ws_transform.e

# Pick cells at various distances from the western edge of watershed
west_edge = ws_x.min()
print(f"Western edge of watershed: X={west_edge:.0f}")
print(f"DEM left edge: X={dem_bounds.left:.0f}")
print(f"Watershed extent: {ws_x.min():.0f} to {ws_x.max():.0f} ({(ws_x.max()-ws_x.min())/1000:.1f} km)")

# Sample at different bands: edge, 100m in, 500m in, 1km in, 2km in, 5km in
for offset_m in [0, 100, 500, 1000, 2000, 5000]:
    target_x = west_edge + offset_m
    # Find cells near this X, pick a few at different Y positions
    mask = (ws_x >= target_x - 10) & (ws_x <= target_x + 10)
    if not mask.any():
        print(f"\n  Offset {offset_m}m: no cells at X≈{target_x:.0f}")
        continue
    
    candidates_x = ws_x[mask]
    candidates_y = ws_y[mask]
    candidates_r = ws_rows[mask]
    candidates_c = ws_cols[mask]
    
    # Pick 3 spread across Y
    n_pick = min(3, len(candidates_x))
    y_sorted_idx = np.argsort(candidates_y)
    pick_idx = [y_sorted_idx[0], y_sorted_idx[len(y_sorted_idx)//2], y_sorted_idx[-1]][:n_pick]
    
    results = []
    for j in pick_idx:
        r, c = candidates_r[j], candidates_c[j]
        path, reason = trace_flow(r, c)
        end_r, end_c = path[-1]
        end_x = d8_transform.c + (end_c + 0.5) * d8_transform.a
        end_y = d8_transform.f + (end_r + 0.5) * d8_transform.e
        end_pt = Point(end_x, end_y)
        in_comm = comm_polygon.contains(end_pt)
        in_parcel = parcel_polygon.contains(end_pt)
        results.append((len(path), reason, in_comm, in_parcel, end_x, end_y))
    
    hit_comm = sum(1 for _, _, c, _, _, _ in results if c)
    print(f"  Offset {offset_m:>5}m: {hit_comm}/{len(results)} reach community", end="")
    for steps, reason, in_c, in_p, ex, ey in results:
        print(f" [{steps} steps, {reason}, comm={in_c}, parcel={in_p}]", end="")
    print()
