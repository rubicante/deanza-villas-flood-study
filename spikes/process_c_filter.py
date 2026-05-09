"""Process C: D8 reachability filter, rlimit 4 GB."""
import os, sys, time, resource, gc
import numpy as np
import rasterio
import geopandas as gpd
from rasterio import features
from pathlib import Path

GB = 1024**3
resource.setrlimit(resource.RLIMIT_AS, (4 * GB, 4 * GB))

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
HENDERSON = ROOT / "data" / "derived" / "henderson"
MAPS = ROOT / "outputs" / "maps"
STREAMS = HENDERSON / "streams_d8_1m_250.tif"
PTR = HENDERSON / "d8_pointer_1m.tif"
PARCEL = ROOT / "data" / "raw" / "sangis" / "deanza_villas_complex_boundary.geojson"
ACCUM = HENDERSON / "d8_flow_accum_1m.tif"
BIN_OUT = MAPS / "streams_d8_1m.bin"
BOUNDARY = ROOT / "data" / "derived" / "vectors" / "henderson_watershed_boundary.geojson"

D8_DELTA = {
    1: (-1, 1), 2: (0, 1), 4: (1, 1), 8: (1, 0),
    16: (1, -1), 32: (0, -1), 64: (-1, -1), 128: (-1, 0),
}

t0 = time.time()
print(f"Process C: D8 reachability filter, OMP={os.environ.get('OMP_NUM_THREADS','?')}")

# Load streams and pointer
with rasterio.open(STREAMS) as src:
    streams = src.read(1)
    s_profile = src.profile
    s_crs = src.crs
    s_transform = src.transform
    s_shape = src.shape
print(f"  Streams: {s_shape}, {(streams>0).sum():,} cells")

with rasterio.open(PTR) as src:
    ptr = src.read(1)
    assert ptr.shape == s_shape

# Rasterize parcel
parcel = gpd.read_file(PARCEL).to_crs(s_crs)
target_geom = parcel.geometry.iloc[0].buffer(3.0)
del parcel; gc.collect()

target_mask = features.rasterize(
    [(target_geom, 1)],
    out_shape=s_shape, transform=s_transform, dtype="uint8"
)
print(f"  Target: {target_mask.sum():,} cells")

# Reachability trace
cache = np.zeros(s_shape, dtype=np.uint8)
stream_cells = np.argwhere(streams > 0)
result = np.zeros(s_shape, dtype=bool)
n_traced = 0; n_cache_hits = 0

for r, c in stream_cells:
    # Check cache
    cv = cache[r, c]
    if cv:
        result[r, c] = cv == 1
        n_cache_hits += 1
        continue

    # Trace
    visited = set()
    path = [(r, c)]
    tr, tc = r, c
    reached = False

    while True:
        cv2 = cache[tr, tc]
        if cv2:
            reached = cv2 == 1
            break
        if target_mask[tr, tc]:
            reached = True
            break
        if (tr, tc) in visited:
            reached = False
            break
        visited.add((tr, tc))
        n_traced += 1
        code = int(ptr[tr, tc])
        if code == 0 or code not in D8_DELTA:
            reached = False
            break
        dr, dc = D8_DELTA[code]
        tr, tc = tr + dr, tc + dc
        if tr < 0 or tr >= s_shape[0] or tc < 0 or tc >= s_shape[1]:
            reached = False
            break
        path.append((tr, tc))

    val = 1 if reached else 2
    for pr, pc in path:
        cache[pr, pc] = val
    result[r, c] = reached

n_reaching = int(result.sum())
n_stream = len(stream_cells)
print(f"  D8 reachable: {n_reaching:,}/{n_stream:,} ({n_reaching/n_stream*100:.1f}%)")
print(f"  Traced: {n_traced:,}, cache hits: {n_cache_hits:,}")

# Write filtered streams
filtered = np.where(result, streams, 0).astype("uint8")
reachable_out = HENDERSON / "streams_d8_1m_250_reachable.tif"
prof = s_profile.copy()
prof.update(dtype="uint8", compress="lzw", nodata=0, bigtiff="YES")
with rasterio.open(reachable_out, "w", **prof) as dst:
    dst.write(filtered, 1)

# Binary export
import struct
from rasterio.warp import transform as rio_transform
rows_s, cols_s = np.where(filtered > 0)
n_cells = len(rows_s)
xs = s_transform.c + (cols_s + 0.5) * s_transform.a
ys = s_transform.f + (rows_s + 0.5) * s_transform.e
lons, lats = rio_transform(s_crs, "EPSG:4326", xs, ys)
lons = np.asarray(lons); lats = np.asarray(lats)
accums = np.zeros(n_cells)  # placeholder — we don't have accum loaded; skip accum values
# Actually we need accum for binary export. Load it.
with rasterio.open(ACCUM) as src:
    accum_data = src.read(1)
accums = accum_data[rows_s, cols_s]
order = np.argsort(accums)[::-1]
accums = accums[order]; lons = lons[order]; lats = lats[order]

with open(BIN_OUT, "wb") as f:
    f.write(struct.pack("I", n_cells))
    for i in range(n_cells):
        f.write(struct.pack("fff", float(accums[i]), float(lons[i]), float(lats[i])))

elapsed = time.time() - t0
rusage = resource.getrusage(resource.RUSAGE_SELF)
peak_mb = rusage.ru_maxrss / 1024
print(f"Process C done: {elapsed:.0f}s, peak RSS: {peak_mb:.0f} MB, bin: {BIN_OUT.stat().st_size/1e6:.1f} MB")
