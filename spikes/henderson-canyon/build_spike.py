"""Spike: Henderson Canyon watershed D∞ flow to parcel.
10m DEM, full watershed → D∞ accumulation → binary for visualization.
All artifacts in spikes/henderson-canyon/.
"""
from pathlib import Path
import struct, time

import numpy as np
import py3dep
import rasterio
from rasterio.warp import transform_bounds, Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject
from whitebox.whitebox_tools import WhiteboxTools

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
SPIKE = ROOT / "spikes" / "henderson-canyon"
SPIKE.mkdir(parents=True, exist_ok=True)

# BBox: Henderson Canyon headwaters to NW + valley floor past parcel
# EPSG:4326
BBOX_4326 = (-116.50, 33.26, -116.35, 33.40)
RES = 0.000089831  # ~10m at this latitude
TARGET_CRS = "EPSG:5070"

print(f"BBOX 4326: {BBOX_4326}")
print(f"Resolution: {RES:.8f}° (~10m)")

# ── Step 1: Fetch 10m DEM ──
dem_10m = SPIKE / "dem_10m_4326.tif"
if not dem_10m.exists():
    t0 = time.time()
    print("Fetching 10m DEM via py3dep...")
    dem = py3dep.get_dem(BBOX_4326, resolution=10, crs=4326)
    dem.rio.to_raster(dem_10m)
    print(f"  {dem_10m.stat().st_size/1e6:.0f}MB in {time.time()-t0:.0f}s")
else:
    print(f"  Using cached {dem_10m}")

# ── Step 2: Already in EPSG:5070 (py3dep returned native CRS) — use as-is ──
with rasterio.open(dem_10m) as src:
    width, height = src.width, src.height
    print(f"  DEM: {width}x{height} ({width*height/1e6:.1f}M px), CRS={src.crs}, res={src.res[0]:.1f}m")
    # Verify coverage
    b4326 = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
    print(f"  Covers: ({b4326[0]:.4f}, {b4326[1]:.4f}, {b4326[2]:.4f}, {b4326[3]:.4f})")

dem_working = dem_10m  # use as-is, already 5070

# ── Step 3: Breach + fill ──
wbt = WhiteboxTools()
wbt.set_working_dir(str(SPIKE))
wbt.set_verbose_mode(False)

breached = SPIKE / "dem_breached.tif"
filled = SPIKE / "dem_filled_breached.tif"

if not breached.exists():
    t0 = time.time()
    wbt.breach_depressions(str(dem_working), str(breached), max_length=500)
    print(f"  Breached in {time.time()-t0:.0f}s")
if not filled.exists():
    t0 = time.time()
    wbt.fill_depressions(str(breached), str(filled), fix_flats=True)
    print(f"  Filled in {time.time()-t0:.0f}s")

# ── Step 4: D∞ flow accumulation ──
dinf_accum = SPIKE / "dinf_flow_accum.tif"
if not dinf_accum.exists():
    t0 = time.time()
    print("  DInfFlowAccumulation...")
    wbt.d_inf_flow_accumulation(str(filled), str(dinf_accum), out_type="cells")
    print(f"  Done in {time.time()-t0:.0f}s")

# ── Step 5: Extract streams at threshold 100, 500, 1000, 5000 (10m DEM → lower thresholds) ──
for t_val in [100, 500, 1000, 5000]:
    streams = SPIKE / f"streams_{t_val}.tif"
    if not streams.exists():
        wbt.extract_streams(str(dinf_accum), str(streams), t_val, zero_background=True)
        with rasterio.open(streams) as s:
            cells = int((s.read(1) > 0).sum())
        print(f"  Streams t={t_val}: {cells:,} cells")

# ── Step 6: Export binary at threshold 100 (dense for visualization) ──
streams_100 = SPIKE / "streams_100.tif"
binary_path = SPIKE / "threshold_dinf_sorted.bin"
if not binary_path.exists():
    t0 = time.time()
    with rasterio.open(streams_100) as src:
        sdata = src.read(1)
        transform_s = src.transform
    with rasterio.open(dinf_accum) as src:
        accum_data = src.read(1)

    rows, cols = np.where(sdata > 0)
    print(f"  Stream cells at t=100: {len(rows):,}")

    # Vectorized coordinate transform: EPSG:5070 → 4326
    xs = transform_s.c + (cols + 0.5) * transform_s.a
    ys = transform_s.f + (rows + 0.5) * transform_s.e
    from rasterio.warp import transform as rio_transform
    lons, lats = rio_transform(TARGET_CRS, "EPSG:4326", xs, ys)

    triples = list(zip(accum_data[rows, cols], lons, lats))
    triples.sort(key=lambda t: t[0], reverse=True)

    with open(binary_path, "wb") as f:
        f.write(struct.pack("I", len(triples)))
        for accum, lon, lat in triples:
            f.write(struct.pack("fff", float(accum), float(lon), float(lat)))

    print(f"  Binary: {len(triples):,} cells, {binary_path.stat().st_size/1e6:.1f}MB in {time.time()-t0:.0f}s")

# ── Summary ──
print(f"\n=== Spike artifacts ===")
for p in sorted(SPIKE.glob("*")):
    if p.is_file():
        print(f"  {p.name:45s} {p.stat().st_size/1e6:7.1f}MB")
print(f"\nBinary: {binary_path}")
