"""Check DEM values and flow direction at canyon headwater vs community."""
import numpy as np
from pathlib import Path
import rasterio

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
SPIKE = ROOT / "spikes" / "henderson-canyon"

with rasterio.open(SPIKE / "dem_filled_breached.tif") as src:
    dem = src.read(1)
    dem_crs = src.crs
    dem_transform = src.transform

with rasterio.open(SPIKE / "dinf_pointer.tif") as src:
    dinf_ptr = src.read(1)

# Canyon headwater cell (from trace)
# Start: (-1874306, 1347349) in EPSG:5070
# Convert to row/col
col = int((-1874306 - dem_transform.c) / dem_transform.a)
row = int((1347349 - dem_transform.f) / dem_transform.e)

print(f"Canyon headwater: row={row}, col={col}")
print(f"  DEM elev: {dem[row, col]:.1f}m")
print(f"  D∞ angle: {dinf_ptr[row, col]:.1f}°")

# Community center: ~(-1872287, 1337292)
ccol = int((-1872287 - dem_transform.c) / dem_transform.a)
crow = int((1337292 - dem_transform.f) / dem_transform.e)
print(f"\nCommunity center: row={crow}, col={ccol}")
print(f"  DEM elev: {dem[crow, ccol]:.1f}m")

# Check a few cells around canyon headwater - elevation trend
print("\nElevation around canyon headwater:")
for dr in range(-2, 3):
    for dc in range(-2, 3):
        if 0 <= row+dr < dem.shape[0] and 0 <= col+dc < dem.shape[1]:
            e = dem[row+dr, col+dc]
            d = dinf_ptr[row+dr, col+dc]
            if 0 < d <= 360:
                print(f"  ({row+dr},{col+dc}) elev={e:.1f}m  D∞={d:.0f}°")
            else:
                print(f"  ({row+dr},{col+dc}) elev={e:.1f}m  D∞=nodata")

# Check: what is the minimum elevation cell near community?
# Community area
c_min_row = max(0, crow-50)
c_max_row = min(dem.shape[0], crow+50)
c_min_col = max(0, ccol-50)
c_max_col = min(dem.shape[1], ccol+50)
patch = dem[c_min_row:c_max_row, c_min_col:c_max_col]
print(f"\nCommunity area elevations: min={patch.min():.1f}m, max={patch.max():.1f}m, mean={patch.mean():.1f}m")

# Canyon area elevations  
ca_min_row = max(0, row-50)
ca_max_row = min(dem.shape[0], row+50)
ca_min_col = max(0, col-50)
ca_max_col = min(dem.shape[1], col+50)
patch2 = dem[ca_min_row:ca_max_row, ca_min_col:ca_max_col]
print(f"Canyon area elevations: min={patch2.min():.1f}m, max={patch2.max():.1f}m, mean={patch2.mean():.1f}m")

# Elevation difference
print(f"\nCanyon is {dem[row,col] - patch.mean():.0f}m above community area")
print(f"Flow should go FROM canyon (higher) TO community (lower)")

# Check: is the DEM actually inverted? (lower elevations in mountains?)
print(f"\nCanyon max elev: {patch2.max():.1f}m")
print(f"Community max elev: {patch.max():.1f}m")
