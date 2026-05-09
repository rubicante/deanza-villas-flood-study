"""Process D: D∞ 1m watershed mask, stream re-extraction, reachability, binary export."""
import os, sys, time, resource, gc, struct
import numpy as np
import rasterio
from rasterio import features
from rasterio.warp import transform as rio_transform
import geopandas as gpd
from pathlib import Path
from whitebox.whitebox_tools import WhiteboxTools

GB = 1024**3
resource.setrlimit(resource.RLIMIT_AS, (5 * GB, 5 * GB))

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
sys.path.insert(0, str(ROOT))
HENDERSON = ROOT / "data" / "derived" / "henderson"
MAPS = ROOT / "outputs" / "maps"
WS_BOUNDARY_5070 = ROOT / "data" / "derived" / "vectors" / "henderson_watershed_boundary_5070.geojson"
PARCEL = ROOT / "data" / "raw" / "sangis" / "deanza_villas_complex_boundary.geojson"
BOUNDARY = ROOT / "data" / "derived" / "vectors" / "henderson_watershed_boundary.geojson"

ACCUM = HENDERSON / "dinf_flow_accum_1m.tif"
ACCUM_MASKED = HENDERSON / "dinf_flow_accum_1m_masked.tif"
PTR = HENDERSON / "dinf_pointer_1m.tif"
STREAMS = HENDERSON / "streams_dinf_1m_250.tif"
BIN_OUT = MAPS / "streams_all.bin"

t0 = time.time()
print(f"Process D: D∞ 1m watershed mask + reachability, OMP={os.environ.get('OMP_NUM_THREADS','?')}")

# ── Step 1: Load grid metadata ──
with rasterio.open(ACCUM) as src:
    accum = src.read(1)
    profile = src.profile.copy()
    shape = src.shape
    transform = src.transform
    crs = src.crs
print(f"  Accum: {shape}, max={accum.max():.0f}")
del accum; gc.collect()

# ── Step 2: Rasterize watershed boundary ──
ws_gdf = gpd.read_file(WS_BOUNDARY_5070)
ws_mask = features.rasterize(
    [(ws_gdf.geometry.iloc[0], 1)],
    out_shape=shape,
    transform=transform,
    dtype="uint8",
)
n_ws = int(ws_mask.sum())
pct = n_ws / shape[0] / shape[1] * 100
print(f"  Watershed mask: {n_ws:,} cells ({pct:.1f}% of grid)")
del ws_gdf; gc.collect()

# ── Step 3: Mask accumulation to watershed ──
with rasterio.open(ACCUM) as src:
    accum = src.read(1)
masked = np.where(ws_mask > 0, accum, 0.0).astype("float32")
del accum; gc.collect()
profile.update(compress="lzw", bigtiff="YES")
with rasterio.open(ACCUM_MASKED, "w", **profile) as dst:
    dst.write(masked, 1)
print(f"  Masked accum: {(masked>0).sum():,} nonzero → {ACCUM_MASKED.name}")
del masked; gc.collect()

# ── Step 4: Re-extract streams from masked accum ──
wbt = WhiteboxTools()
wbt.set_working_dir(str(HENDERSON))
wbt.set_verbose_mode(False)
wbt.extract_streams(str(ACCUM_MASKED.resolve()), str(STREAMS.resolve()), 250, zero_background=True)

# Convert to uint8
with rasterio.open(STREAMS) as src:
    sdata = src.read(1)
    sprof = src.profile.copy()
n_stream = int((sdata > 0).sum())
uint8_data = (sdata > 0).astype("uint8")
sprof.update(dtype="uint8", compress="lzw", nodata=0, bigtiff="YES")
with rasterio.open(STREAMS, "w", **sprof) as dst:
    dst.write(uint8_data, 1)
print(f"  Streams (t=250): {n_stream:,} cells, uint8 → {STREAMS.name}")
del sdata, uint8_data; gc.collect()

# ── Step 5: Reachability filter ──
from deliverable.reachability import filter_reachable

filtered_path = HENDERSON / "streams_dinf_1m_250_reachable.tif"
filter_reachable(STREAMS, PTR, PARCEL, output=filtered_path, pointer_type="dinf")

with rasterio.open(filtered_path) as src:
    fdata = src.read(1)
n_reachable = int((fdata > 0).sum())
print(f"  Reachable: {n_reachable:,}/{n_stream:,} ({n_reachable/n_stream*100:.1f}%)")

# ── Step 6: Binary export ──
with rasterio.open(ACCUM_MASKED) as src:
    accum_data = src.read(1)
    transform_acc = src.transform

rows_s, cols_s = np.where(fdata > 0)
n_cells = len(rows_s)
xs = transform_acc.c + (cols_s + 0.5) * transform_acc.a
ys = transform_acc.f + (rows_s + 0.5) * transform_acc.e
lons, lats = rio_transform(crs, "EPSG:4326", xs, ys)
lons = np.asarray(lons, dtype="float64")
lats = np.asarray(lats, dtype="float64")
accums = accum_data[rows_s, cols_s]
order = np.argsort(accums)[::-1]
accums = accums[order]
lons = lons[order]
lats = lats[order]

assert np.sum(np.isinf(accums)) == 0, "inf in export"
assert np.sum(np.isnan(accums)) == 0, "nan in export"

with open(BIN_OUT, "wb") as f:
    f.write(struct.pack("I", n_cells))
    for i in range(n_cells):
        f.write(struct.pack("fff", float(accums[i]), float(lons[i]), float(lats[i])))

# Boundary sanity check
ws_boundary = gpd.read_file(BOUNDARY)
ws_bounds = ws_boundary.to_crs("EPSG:4326").total_bounds
assert ws_bounds[0] <= lons[0] <= ws_bounds[2], "first lon outside boundary"
assert ws_bounds[1] <= lats[0] <= ws_bounds[3], "first lat outside boundary"

elapsed = time.time() - t0
rusage = resource.getrusage(resource.RUSAGE_SELF)
peak_mb = rusage.ru_maxrss / 1024
fsize = BIN_OUT.stat().st_size / 1e6
print(f"Process D done: {elapsed:.0f}s, peak RSS: {peak_mb:.0f} MB, bin: {fsize:.1f} MB ({n_cells:,} cells)")
