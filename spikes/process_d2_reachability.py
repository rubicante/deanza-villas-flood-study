"""Process D part 2: D∞ reachability filter + binary export (mask + streams already done)."""
import os, sys, time, resource, gc, struct
import numpy as np
import rasterio
from rasterio.warp import transform as rio_transform
import geopandas as gpd
from pathlib import Path

GB = 1024**3
resource.setrlimit(resource.RLIMIT_AS, (5 * GB, 5 * GB))

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
sys.path.insert(0, str(ROOT))

HENDERSON = ROOT / "data" / "derived" / "henderson"
MAPS = ROOT / "outputs" / "maps"
PARCEL = ROOT / "data" / "raw" / "sangis" / "deanza_villas_complex_boundary.geojson"
BOUNDARY = ROOT / "data" / "derived" / "vectors" / "henderson_watershed_boundary.geojson"

ACCUM_MASKED = HENDERSON / "dinf_flow_accum_1m_masked.tif"
PTR = HENDERSON / "dinf_pointer_1m.tif"
STREAMS = HENDERSON / "streams_dinf_1m_250.tif"
BIN_OUT = MAPS / "streams_all.bin"

t0 = time.time()
print(f"Process D part 2: D∞ reachability + export, OMP={os.environ.get('OMP_NUM_THREADS','?')}")

# ── Reachability filter ──
from deliverable.reachability import filter_reachable

filtered_path = HENDERSON / "streams_dinf_1m_250_reachable.tif"
filter_reachable(STREAMS, PTR, PARCEL, output=filtered_path, pointer_type="dinf")

with rasterio.open(STREAMS) as src:
    sdata = src.read(1)
n_stream = int((sdata > 0).sum())

with rasterio.open(filtered_path) as src:
    fdata = src.read(1)
    fprof = src.profile
n_reachable = int((fdata > 0).sum())
print(f"  Reachable: {n_reachable:,}/{n_stream:,} ({n_reachable/n_stream*100:.1f}%)")

# ── Binary export ──
with rasterio.open(ACCUM_MASKED) as src:
    accum_data = src.read(1)
    transform_acc = src.transform
    crs = src.crs

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

# Boundary sanity
ws_boundary = gpd.read_file(BOUNDARY)
ws_bounds = ws_boundary.to_crs("EPSG:4326").total_bounds
assert ws_bounds[0] <= lons[0] <= ws_bounds[2], "first lon outside boundary"
assert ws_bounds[1] <= lats[0] <= ws_bounds[3], "first lat outside boundary"

elapsed = time.time() - t0
rusage = resource.getrusage(resource.RUSAGE_SELF)
peak_mb = rusage.ru_maxrss / 1024
fsize = BIN_OUT.stat().st_size / 1e6
print(f"Process D done: {elapsed:.0f}s, peak RSS: {peak_mb:.0f} MB, bin: {fsize:.1f} MB ({n_cells:,} cells)")
