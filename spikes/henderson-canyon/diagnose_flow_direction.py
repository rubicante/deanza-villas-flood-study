"""Diagnostic: trace downstream from Henderson Canyon headwater to verify connectivity."""
import numpy as np
from pathlib import Path
import rasterio
from shapely.geometry import Point
import geopandas as gpd
import math

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
SPIKE = ROOT / "spikes" / "henderson-canyon"

# Load D∞ pointer and accumulation
with rasterio.open(SPIKE / "dinf_pointer.tif") as src:
    dinf_ptr = src.read(1)
    crs = src.crs
    transform = src.transform
    nodata = src.nodata

with rasterio.open(SPIKE / "dinf_flow_accum.tif") as src:
    dinf_accum = src.read(1)

# Community bbox
comm = gpd.read_file(ROOT / "outputs/maps/deanza_community_poi.geojson")
comm_5070 = comm.to_crs(crs)
comm_polygon = comm_5070.geometry.iloc[0]
comm_bounds = comm_5070.total_bounds

print(f"D∞ pointer: shape={dinf_ptr.shape}, nodata={nodata}")
print(f"Community bounds (EPSG:5070): {comm_bounds}")
print(f"Community center: {comm_5070.centroid.x.iloc[0]:.0f}, {comm_5070.centroid.y.iloc[0]:.0f}")

# Find high-accumulation cells in the mountain area (west of community, inside HUC)
# Henderson Canyon headwaters should be west/northwest of community, 
# at higher elevation (more negative X = farther west in EPSG:5070)
# Pick cells with high accumulation in the western area

# Mask: west of community bbox, high accumulation
comm_west = comm_bounds[0]  # left edge of community
mask = (dinf_accum > 1000)  # high accumulation = established channels

rows, cols = np.where(mask)
x_coords = transform.c + (cols + 0.5) * transform.a

# Filter to cells well west of community (at least 1km)
west_mask = x_coords < (comm_west - 1000)
west_rows = rows[west_mask]
west_cols = cols[west_mask]
west_accum = dinf_accum[rows[west_mask], cols[west_mask]]

print(f"\nHigh-accum cells west of community: {len(west_rows)}")

# Pick top 5 by accumulation (deepest channels)
top_idx = np.argsort(west_accum)[-5:][::-1]
print("\nTop 5 western channel cells:")
for i in top_idx:
    r, c = west_rows[i], west_cols[i]
    x = transform.c + (c + 0.5) * transform.a
    y = transform.f + (r + 0.5) * transform.e
    accum = dinf_accum[r, c]
    print(f"  ({x:.0f}, {y:.0f}) accum={accum:.0f}")

# D∞ downstream trace: follow the flow direction
# D∞ partitions flow to two adjacent cardinal directions based on angle
def d_inf_downstream_neighbors(r, c):
    """Return list of (nr, nc, fraction) for D∞ flow from (r,c)."""
    angle_deg = dinf_ptr[r, c]
    if angle_deg <= 0 or angle_deg > 360:
        return []
    
    angle_rad = math.radians(angle_deg)
    # Normalize to [0, 2π)
    angle_rad = angle_rad % (2 * math.pi)
    
    # Cardinal directions in radians CCW from east
    card_angles = [0, math.pi/4, math.pi/2, 3*math.pi/4, math.pi, 
                   -3*math.pi/4, -math.pi/2, -math.pi/4]
    card_offsets = [(0,1), (-1,1), (-1,0), (-1,-1), (0,-1), (1,-1), (1,0), (1,1)]
    
    # Find the two sectors bracketing the angle
    for i in range(8):
        a1 = card_angles[i] % (2*math.pi)
        a2 = card_angles[(i+1) % 8] % (2*math.pi)
        
        between = False
        if a1 <= a2:
            between = a1 <= angle_rad <= a2
        else:
            between = angle_rad >= a1 or angle_rad <= a2
        
        if between:
            dr1, dc1 = card_offsets[i]
            dr2, dc2 = card_offsets[(i+1) % 8]
            # Fraction to first direction
            if a1 == a2:
                frac = 1.0
            else:
                # angular distance from a1
                if a1 <= a2:
                    frac = 1.0 - (angle_rad - a1) / (a2 - a1)
                else:
                    dist = (angle_rad - a1) % (2*math.pi)
                    total = (a2 - a1) % (2*math.pi)
                    frac = 1.0 - dist / total if total > 0 else 1.0
            
            result = []
            if frac > 0:
                result.append((r + dr1, c + dc1, frac))
            if frac < 1:
                result.append((r + dr2, c + dc2, 1.0 - frac))
            return result
    
    return []

# Trace from top channel cell following dominant direction
def trace_downstream(r, c, max_steps=20000):
    path = [(r, c)]
    for _ in range(max_steps):
        if r < 0 or r >= dinf_ptr.shape[0] or c < 0 or c >= dinf_ptr.shape[1]:
            return path, "exited_raster"
        neighbors = d_inf_downstream_neighbors(r, c)
        if not neighbors:
            return path, "no_flow"
        # Follow the dominant fraction
        best = max(neighbors, key=lambda n: n[2])
        nr, nc, _ = best
        if nr == r and nc == c:
            return path, "stuck"
        r, c = nr, nc
        path.append((r, c))
    return path, "max_steps"

# Trace from each of the top 5
print("\n=== DOWNSTREAM TRACE ===")
for idx in top_idx:
    r, c = west_rows[idx], west_cols[idx]
    sx = transform.c + (c + 0.5) * transform.a
    sy = transform.f + (r + 0.5) * transform.e
    accum = dinf_accum[r, c]
    
    path, reason = trace_downstream(r, c)
    end_r, end_c = path[-1]
    ex = transform.c + (end_c + 0.5) * transform.a
    ey = transform.f + (end_r + 0.5) * transform.e
    end_pt = Point(ex, ey)
    
    in_comm = comm_polygon.contains(end_pt)
    dist_to_comm = end_pt.distance(comm_polygon.centroid)
    
    # Also check if any intermediate point hits community
    hit_comm = False
    hit_step = -1
    for i, (pr, pc) in enumerate(path):
        px = transform.c + (pc + 0.5) * transform.a
        py = transform.f + (pr + 0.5) * transform.e
        if comm_polygon.contains(Point(px, py)):
            hit_comm = True
            hit_step = i
            break
    
    print(f"\nStart: ({sx:.0f}, {sy:.0f}) accum={accum:.0f}")
    print(f"  Path: {len(path)} steps, reason: {reason}")
    print(f"  End: ({ex:.0f}, {ey:.0f}) {dist_to_comm/1000:.1f}km from community center")
    print(f"  Hit community en route: {hit_comm}" + (f" at step {hit_step}" if hit_comm else ""))
    print(f"  Terminal in community: {in_comm}")
    
    # Show first 5 and last 5 steps
    for i, (pr, pc) in enumerate(path[:5]):
        px = transform.c + (pc + 0.5) * transform.a
        py = transform.f + (pr + 0.5) * transform.e
        print(f"    [{i}] ({px:.0f}, {py:.0f})")
    if len(path) > 10:
        print(f"    ...")
    for i, (pr, pc) in enumerate(path[-3:]):
        px = transform.c + (pc + 0.5) * transform.a
        py = transform.f + (pr + 0.5) * transform.e
        print(f"    [{len(path)-3+i}] ({px:.0f}, {py:.0f})")
