"""Process A (v3): Watershed-clipped D8 accumulation, rlimit 6 GB."""
import os, sys, time, resource, gc
import numpy as np
import rasterio
from rasterio import features
import geopandas as gpd
from pathlib import Path

GB = 1024**3
resource.setrlimit(resource.RLIMIT_AS, (5 * GB, 5 * GB))

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
HENDERSON = ROOT / "data" / "derived" / "henderson"
DEM = HENDERSON / "dem_1m_filled_f32.tif"
PTR = HENDERSON / "d8_pointer_1m.tif"
WS_BOUNDARY = ROOT / "data" / "derived" / "vectors" / "henderson_watershed_boundary_5070.geojson"
ACCUM_OUT = HENDERSON / "d8_flow_accum_1m.tif"

_WBT_TO_PYFLWDIR = np.zeros(256, dtype="uint8")
_WBT_TO_PYFLWDIR[1] = 128; _WBT_TO_PYFLWDIR[2] = 1; _WBT_TO_PYFLWDIR[4] = 2
_WBT_TO_PYFLWDIR[8] = 4; _WBT_TO_PYFLWDIR[16] = 8; _WBT_TO_PYFLWDIR[32] = 16
_WBT_TO_PYFLWDIR[64] = 32; _WBT_TO_PYFLWDIR[128] = 64

t0 = time.time()
print(f"Process A v3: watershed-clipped, OMP={os.environ.get('OMP_NUM_THREADS','?')}")

# Load DEM profile
with rasterio.open(DEM) as src:
    profile = src.profile
    shape = src.shape
    transform = src.transform
print(f"  DEM: {shape}")

# Rasterize watershed boundary at 1m
ws_gdf = gpd.read_file(WS_BOUNDARY)
ws_mask = features.rasterize(
    [(ws_gdf.geometry.iloc[0], 1)],
    out_shape=shape,
    transform=transform,
    dtype="uint8",
)
n_ws = int(ws_mask.sum())
print(f"  Watershed mask (1m): {n_ws:,} cells ({n_ws/shape[0]/shape[1]*100:.1f}%)")
del ws_gdf; gc.collect()

# Load pointer, mask to watershed, translate
with rasterio.open(PTR) as src:
    ptr = src.read(1).astype('uint8')
ptr[ws_mask == 0] = 0
ptr = _WBT_TO_PYFLWDIR[ptr]
print(f"  Pointer: watershed cells={(ptr>0).sum():,}")

# Build valid mask
valid_mask = ptr > 0
del ws_mask; gc.collect()

# Accumulation via pyflwdir
import pyflwdir
flw = pyflwdir.from_array(ptr, ftype='d8', mask=valid_mask,
                          transform=transform, check_ftype=False)
del ptr; gc.collect()
accum = flw.upstream_area(unit='cell')
print(f"  Accum: max={accum.max():.0f}")

# Place back on full grid
accum_full = np.zeros(shape, dtype="float32")
if accum.ndim == 2:
    accum_full[valid_mask] = accum[valid_mask]
else:
    accum_full[valid_mask] = accum
del accum, valid_mask; gc.collect()

profile.update(dtype="float32", compress="lzw", nodata=0.0, bigtiff="YES")
with rasterio.open(ACCUM_OUT, "w", **profile) as dst:
    dst.write(accum_full, 1)

elapsed = time.time() - t0
rusage = resource.getrusage(resource.RUSAGE_SELF)
peak_mb = rusage.ru_maxrss / 1024
print(f"Process A done: {elapsed:.0f}s, peak RSS: {peak_mb:.0f} MB")
