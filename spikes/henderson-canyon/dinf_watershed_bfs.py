"""Compute D∞ pointer, then BFS upstream trace using D∞ continuous angles."""
import numpy as np
from pathlib import Path
import rasterio
from rasterio import features
import geopandas as gpd
from shapely.geometry import Point
from collections import deque
from whitebox.whitebox_tools import WhiteboxTools

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
SPIKE = ROOT / "spikes" / "henderson-canyon"

# ── Step 1: Compute D∞ pointer ──
dinf_ptr_path = SPIKE / "dinf_pointer.tif"
if not dinf_ptr_path.exists():
    print("Computing D∞ pointer...")
    wbt = WhiteboxTools()
    wbt.set_working_dir(str(SPIKE))
    wbt.set_verbose_mode(False)
    wbt.d_inf_pointer(str(SPIKE / "dem_filled_breached.tif"), str(dinf_ptr_path))
    print(f"  Saved: {dinf_ptr_path}")
else:
    print(f"D∞ pointer exists: {dinf_ptr_path}")

# ── Step 2: Load rasters ──
with rasterio.open(dinf_ptr_path) as src:
    dinf_ptr = src.read(1)
    crs = src.crs
    transform = src.transform
    nodata = src.nodata
    print(f"D∞ pointer: shape={dinf_ptr.shape}, nodata={nodata}")
    print(f"  Valid range: [{dinf_ptr[dinf_ptr>nodata].min():.3f}, {dinf_ptr[dinf_ptr>nodata].max():.3f}]")

# ── Step 3: Rasterize community pour points ──
comm = gpd.read_file(ROOT / "outputs/maps/deanza_community_poi.geojson")
comm_5070 = comm.to_crs(crs)
comm_rast = features.rasterize(
    [(comm_5070.geometry.iloc[0], 1)],
    out_shape=dinf_ptr.shape,
    transform=transform,
    dtype='uint8'
)
pour_cells = np.where(comm_rast > 0)
print(f"Community pour cells: {len(pour_cells[0]):,}")

# ── Step 4: D∞ upstream neighbor check ──
# D∞ angle: radians CCW from east (positive = north, negative = south).
# WBT DInfPointer format: angle in radians CCW from east.
# 
# For a neighbor at relative position (dr, dc) where:
#   (-1,-1)=NW, (-1,0)=N, (-1,1)=NE, (0,-1)=W, (0,1)=E,
#   (1,-1)=SW, (1,0)=S, (1,1)=SE
#
# We need to know: does the neighbor's D∞ angle θ partition flow 
# toward the center cell (0,0)?
#
# D∞ partitions flow to the two adjacent cardinal directions bracketing θ.
# The 8 directions in radians CCW from east:
#   E:  0
#   NE: π/4 ≈ 0.785
#   N:  π/2 ≈ 1.571
#   NW: 3π/4 ≈ 2.356
#   W:  π ≈ 3.142 (or -π)
#   SW: -3π/4 ≈ -2.356
#   S:  -π/2 ≈ -1.571
#   SE: -π/4 ≈ -0.785
#
# D∞ angles are in [-π, π]. To check if neighbor at (dr,dc) contributes 
# to center: compute the absolute angle from neighbor to center, then 
# check if the D∞ angle brackets that direction.

import math

# Precompute the angle from each neighbor position to center (r,c)
# Angle in radians CCW from east
neighbor_angles = {}
neighbor_offsets = {
    'NW': (-1,-1), 'N': (-1,0), 'NE': (-1,1),
    'W': (0,-1),                'E': (0,1),
    'SW': (1,-1),  'S': (1,0),  'SE': (1,1)
}

for name, (dr, dc) in neighbor_offsets.items():
    # Angle from neighbor to center: vector (-dr, -dc)
    angle = math.atan2(-dr, -dc)  # atan2(y, x): y=up (negative row), x=right (positive col)
    neighbor_angles[(dr, dc)] = angle

# D∞ partitions to two directions. The two directions are the ones whose 
# angles bracket the D∞ angle. For each neighbor, we need to check if its 
# D∞ angle has the center direction between the two bracketing directions.

# The 8 cardinal angles in radians, in order:
cardinal_angles = [0, math.pi/4, math.pi/2, 3*math.pi/4, math.pi, -3*math.pi/4, -math.pi/2, -math.pi/4]
cardinal_offsets = [(0,1), (-1,1), (-1,0), (-1,-1), (0,-1), (1,-1), (1,0), (1,1)]

def angle_between(angle, a1, a2):
    """Check if 'angle' lies between a1 and a2 (counterclockwise from a1)."""
    # Normalize to [0, 2π)
    angle = angle % (2*math.pi)
    a1 = a1 % (2*math.pi)
    a2 = a2 % (2*math.pi)
    if a1 <= a2:
        return a1 <= angle <= a2
    else:
        return angle >= a1 or angle <= a2

def d_inf_contributes_to_center(dinf_angle_deg, dr, dc):
    """
    Given a neighbor at (dr,dc) from center, and its D∞ angle in DEGREES,
    does this neighbor contribute flow to the center cell?
    """
    # Convert to radians
    angle_rad = math.radians(dinf_angle_deg)
    center_angle = neighbor_angles[(dr, dc)]
    
    # Find the two cardinal sectors bracketing the flow angle.
    # Flow partitions to the two cells at those sector boundaries from the neighbor.
    for i in range(8):
        a1 = cardinal_angles[i]
        a2 = cardinal_angles[(i+1) % 8]
        
        if angle_between(angle_rad, a1, a2):
            off1 = cardinal_offsets[i]
            off2 = cardinal_offsets[(i+1) % 8]
            target = (-dr, -dc)  # vector from neighbor to center
            if off1 == target or off2 == target:
                return True
            break
    return False

# ── Step 5: BFS upstream trace ──
print("Running BFS upstream on D∞ pointer...")
visited = np.zeros(dinf_ptr.shape, dtype=bool)
queue = deque()

# Seed with pour cells
for r, c in zip(*pour_cells):
    if 0 <= r < dinf_ptr.shape[0] and 0 <= c < dinf_ptr.shape[1]:
        if not visited[r, c]:
            visited[r, c] = True
            queue.append((r, c))

iteration = 0
while queue:
    r, c = queue.popleft()
    iteration += 1
    if iteration % 100000 == 0:
        print(f"  {iteration:,} visited, queue={len(queue):,}")
    
    # Check all 8 neighbors
    for (dr, dc) in neighbor_offsets.values():
        nr, nc = r + dr, c + dc
        if nr < 0 or nr >= dinf_ptr.shape[0] or nc < 0 or nc >= dinf_ptr.shape[1]:
            continue
        if visited[nr, nc]:
            continue
        
        dinf_angle = dinf_ptr[nr, nc]
        if nodata is not None and dinf_angle <= nodata:
            continue
        # Filter edge/pit artifacts: D∞ angles should be 0-360 degrees
        if dinf_angle < 0 or dinf_angle > 360:
            continue
        
        if d_inf_contributes_to_center(dinf_angle, dr, dc):
            visited[nr, nc] = True
            queue.append((nr, nc))

bfs_cells = visited.sum()
print(f"\nBFS upstream cells (D∞): {bfs_cells:,}")
print(f"Previous BFS (D8):       47,431")
print(f"WBT watershed() (D8):    948,897")

# ── Step 6: Polygonize ──
print("Polygonizing...")
binary = visited.astype("int16")
results = list(features.shapes(binary, mask=binary.astype("uint8"), transform=transform))
geoms = []
from shapely.geometry import shape
from shapely.ops import unary_union
for g, v in results:
    if v == 1:
        geoms.append(shape(g))

print(f"  {len(geoms)} individual polygons")
merged = unary_union(geoms)
simplified = merged.simplify(10, preserve_topology=True)
area_km2 = merged.area / 1e6
print(f"  Area: {area_km2:.1f} km²")

# ── Step 7: Save GeoJSON ──
gdf_5070 = gpd.GeoDataFrame(
    [{"name": "Henderson Canyon contributing watershed (D∞ BFS)",
      "source": "BFS upstream trace on D∞ pointer + De Anza community pour points",
      "area_km2": round(area_km2, 2),
      "cells": int(bfs_cells),
      "resolution_m": abs(transform.a),
      "note": "Corrected 2026-05-05. D∞ BFS trace replaces both WBT D8 watershed (107 km² false positives) and D8 BFS (4.2 km² false negatives)."}],
    geometry=[simplified],
    crs=crs
)

gdf_4326 = gdf_5070.to_crs("EPSG:4326")
out_path = ROOT / "data/vectors/henderson_watershed_boundary.geojson"
gdf_4326.to_file(out_path, driver="GeoJSON")
print(f"Saved: {out_path}")

bounds = gdf_4326.total_bounds
print(f"WGS84 extent: lon [{bounds[0]:.4f}, {bounds[2]:.4f}], lat [{bounds[1]:.4f}, {bounds[3]:.4f}]")
print(f"E-W: {(bounds[2]-bounds[0])*111.32*0.85:.1f} km, N-S: {(bounds[3]-bounds[1])*111.32:.1f} km")
