"""Diagnostic: compare D8 vs D∞ at canyon headwater cell, verify neighbor elevations."""
import numpy as np
from pathlib import Path
import rasterio

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
SPIKE = ROOT / "spikes" / "henderson-canyon"

# The suspect cell
ROW, COL = 439, 914

# Load all three rasters
with rasterio.open(SPIKE / "dem_filled_breached.tif") as src:
    dem = src.read(1)

with rasterio.open(SPIKE / "d8_pointer.tif") as src:
    d8 = src.read(1)

with rasterio.open(SPIKE / "dinf_pointer.tif") as src:
    dinf = src.read(1)

# CORRECT WBT D8 encoding: 1=NE, 2=E, 4=SE, 8=S, 16=SW, 32=W, 64=NW, 128=N
d8_names = {1:"NE", 2:"E", 4:"SE", 8:"S", 16:"SW", 32:"W", 64:"NW", 128:"N"}
d8_dr = {1:-1, 2:0, 4:1, 8:1, 16:1, 32:0, 64:-1, 128:-1}
d8_dc = {1:1, 2:1, 4:1, 8:0, 16:-1, 32:-1, 64:-1, 128:0}

print(f"=== Cell ({ROW},{COL}) ===")
print(f"Elevation: {dem[ROW,COL]:.1f}m")
print(f"D8 pointer: {d8[ROW,COL]} ({d8_names.get(d8[ROW,COL], 'unknown')})")
print(f"D∞ pointer: {dinf[ROW,COL]:.1f}°")

# Print all 8 neighbor elevations and which neighbor D8 points to
print("\nNeighbors:")
neighbor_labels = {(-1,-1):"NW", (-1,0):"N", (-1,1):"NE", (0,-1):"W", (0,1):"E",
                   (1,-1):"SW", (1,0):"S", (1,1):"SE"}
lowest_elev = float('inf')
lowest_dir = None

for (dr, dc), label in neighbor_labels.items():
    nr, nc = ROW+dr, COL+dc
    if 0 <= nr < dem.shape[0] and 0 <= nc < dem.shape[1]:
        e = dem[nr, nc]
        marker = ""
        if d8[ROW,COL] in d8_names and d8_dr[d8[ROW,COL]] == dr and d8_dc[d8[ROW,COL]] == dc:
            marker = " <-- D8 points here"
        print(f"  {label:3s} ({nr:4d},{nc:4d})  elev={e:7.1f}m{marker}")
        if e < lowest_elev:
            lowest_elev = e
            lowest_dir = label

print(f"\nLowest neighbor: {lowest_dir} at {lowest_elev:.1f}m")
print(f"Drop from center: {dem[ROW,COL] - lowest_elev:.1f}m")

# D8 should point to lowest neighbor
d8_dir = d8_names.get(d8[ROW,COL], "invalid")
d8_nr = ROW + d8_dr.get(d8[ROW,COL], 0)
d8_nc = COL + d8_dc.get(d8[ROW,COL], 0)
if 0 <= d8_nr < dem.shape[0] and 0 <= d8_nc < dem.shape[1]:
    d8_elev = dem[d8_nr, d8_nc]
    print(f"D8 target elev: {d8_elev:.1f}m")
    if d8_elev <= dem[ROW,COL]:
        print(f"D8 is downhill ✓")
    else:
        print(f"D8 is UPHILL! {d8_elev - dem[ROW,COL]:.1f}m higher")
else:
    print(f"D8 points off-raster")

# D∞: 75° CCW from east = 75° north of east
# That's roughly NE (45°) to N (90°)
# Should partition to NE and N
# NE from (439,914) = (438, 915)
ne_r, ne_c = ROW-1, COL+1
n_r, n_c = ROW-1, COL
if 0 <= ne_r < dem.shape[0] and 0 <= ne_c < dem.shape[1]:
    ne_elev = dem[ne_r, ne_c]
    print(f"\nD∞ NE neighbor ({ne_r},{ne_c}): {ne_elev:.1f}m ({'downhill' if ne_elev < dem[ROW,COL] else 'UPHILL' if ne_elev > dem[ROW,COL] else 'flat'})")
if 0 <= n_r < dem.shape[0] and 0 <= n_c < dem.shape[1]:
    n_elev = dem[n_r, n_c]
    print(f"D∞ N neighbor ({n_r},{n_c}): {n_elev:.1f}m ({'downhill' if n_elev < dem[ROW,COL] else 'UPHILL' if n_elev > dem[ROW,COL] else 'flat'})")

# Check: does the lowest neighbor match what D8 says?
print(f"\n=== VERIFICATION ===")
print(f"D8 says flow goes {d8_dir} to ({d8_nr},{d8_nc}) at {d8_elev:.1f}m")
print(f"Lowest neighbor is {lowest_dir} at {lowest_elev:.1f}m")
if d8_dir == lowest_dir:
    print("D8 matches lowest neighbor ✓")
else:
    print(f"D8 MISMATCH: points to {d8_dir} but {lowest_dir} is lower")

# Also check a few cells north of this one to see the gradient trend
print("\n=== Gradient check northward ===")
for dr in range(0, -6, -1):
    nr = ROW + dr
    if 0 <= nr < dem.shape[0]:
        e = dem[nr, COL]
        d = d8[nr, COL]
        print(f"  ({nr:4d},{COL:4d}) elev={e:7.1f}m  D8={d:3d} ({d8_names.get(d, '?')})")

# And westward
print("\n=== Gradient check eastward ===")
for dc in range(0, 6):
    nc = COL + dc
    if 0 <= nc < dem.shape[1]:
        e = dem[ROW, nc]
        d = d8[ROW, nc]
        print(f"  ({ROW:4d},{nc:4d}) elev={e:7.1f}m  D8={d:3d} ({d8_names.get(d, '?')})")
