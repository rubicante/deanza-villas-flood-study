"""Trace D8 flow from westernmost watershed cells to verify they reach the community bbox."""
import numpy as np
from pathlib import Path
import rasterio
import geopandas as gpd
from shapely.geometry import Point

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
SPIKE = ROOT / "spikes" / "henderson-canyon"

# Load rasters
with rasterio.open(SPIKE / "watershed.tif") as src:
    ws_mask = src.read(1)
    ws_crs = src.crs
    ws_transform = src.transform

with rasterio.open(SPIKE / "d8_pointer.tif") as src:
    d8_ptr = src.read(1)
    d8_transform = src.transform

# CORRECT WBT D8 encoding: 1=NE, 2=E, 4=SE, 8=S, 16=SW, 32=W, 64=NW, 128=N
d8_dr = {1:-1, 2:0, 4:1, 8:1, 16:1, 32:0, 64:-1, 128:-1}
d8_dc = {1:1,  2:1, 4:1, 8:0, 16:-1, 32:-1, 64:-1, 128:0}

# Find westernmost watershed cells
ws_rows, ws_cols = np.where(ws_mask > 0)
ws_x = ws_transform.c + (ws_cols + 0.5) * ws_transform.a
westmost_idx = np.argsort(ws_x)[:100]  # top 100 westernmost
west_rows = ws_rows[westmost_idx]
west_cols = ws_cols[westmost_idx]

print(f"Watershed cells: {(ws_mask>0).sum():,}")
print(f"Westernmost X coord: {ws_x.min():.0f}")

def trace_flow(r, c, max_steps=10000):
    """Trace D8 flow from (r,c) to terminal point."""
    path = [(r, c)]
    for _ in range(max_steps):
        if r < 0 or r >= d8_ptr.shape[0] or c < 0 or c >= d8_ptr.shape[1]:
            break
        direction = d8_ptr[r, c]
        if direction <= 0 or direction > 128 or (direction & (direction - 1)) != 0:
            break  # pit or invalid
        r += d8_dr[direction]
        c += d8_dc[direction]
        path.append((r, c))
    return path

# Community bbox
comm = gpd.read_file(ROOT / "outputs/maps/deanza_community_poi.geojson")
comm_5070 = comm.to_crs(ws_crs)
comm_polygon = comm_5070.geometry.iloc[0]

# Also: De Anza Villas parcel
parcel = gpd.read_file(ROOT / "data/vectors/deanza_villas_complex_boundary.geojson")
parcel_5070 = parcel.to_crs(ws_crs)
parcel_polygon = parcel_5070.geometry.iloc[0]

# Trace ALL westernmost cells
reached_comm = 0
reached_parcel = 0
stuck = 0
other = 0
terminal_pts = []

for i, (r, c) in enumerate(zip(west_rows, west_cols)):
    path = trace_flow(r, c)
    end_r, end_c = path[-1]
    end_x = d8_transform.c + (end_c + 0.5) * d8_transform.a
    end_y = d8_transform.f + (end_r + 0.5) * d8_transform.e
    end_pt = Point(end_x, end_y)
    
    in_comm = comm_polygon.contains(end_pt)
    in_parcel = parcel_polygon.contains(end_pt)
    
    if in_comm:
        reached_comm += 1
        if in_parcel:
            reached_parcel += 1
    elif d8_ptr[end_r, end_c] == 0 and len(path) < 10000:
        stuck += 1
    else:
        other += 1
    
    terminal_pts.append((end_x, end_y))
    
    if i < 10:
        start_x = d8_transform.c + (c + 0.5) * d8_transform.a
        start_y = d8_transform.f + (r + 0.5) * d8_transform.e
        print(f"  #{i}: ({start_x:.0f},{start_y:.0f}) -> ({end_x:.0f},{end_y:.0f}) "
              f"[{len(path)} steps] comm={in_comm} parcel={in_parcel}")

print(f"\nResults from {len(west_rows)} westernmost watershed cells:")
print(f"  Reached community bbox:   {reached_comm} ({100*reached_comm/len(west_rows):.0f}%)")
print(f"  Reached De Anza Villas:   {reached_parcel} ({100*reached_parcel/len(west_rows):.0f}%)")
print(f"  Stuck in pit/edge:        {stuck}")
print(f"  Ended outside community:  {other}")

# Where did the "other" cells end up? Show terminal coords in WGS84
if other > 0:
    from rasterio.warp import transform
    print(f"\nCells that DON'T reach community ({other} of {len(west_rows)}):")
    other_idx = [j for j in range(len(west_rows)) if not comm_polygon.contains(Point(terminal_pts[j][0], terminal_pts[j][1]))]
    for j in other_idx[:10]:
        x, y = terminal_pts[j]
        lon, lat = transform(ws_crs, "EPSG:4326", [x], [y])
        print(f"  Terminal: {lon[0]:.4f}, {lat[0]:.4f}")
