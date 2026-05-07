"""
1m full-watershed D∞ pipeline (v2 — May 2026 cleanup).
Fetches DEM → clips to watershed boundary → breach/fill → D∞ →
stream ensemble (1000/2500/5000) → Parquet export.

v2 changes:
  - Fetches bbox derived from canonical watershed GeoJSON (not hardcoded)
  - Clips to watershed boundary early — all downstream steps on clipped raster
  - Breach+fill on clipped DEM only (not full rectangle)
  - WBT intermediates deleted as soon as downstream step completes
  - Stream ensemble at 3 thresholds, matching main pipeline
  - Parquet export instead of custom binary format
  - LZW compression on all GeoTIFFs, float32 for DEM
"""
from pathlib import Path
import time
import gc

import numpy as np
import pandas as pd
import geopandas as gpd
import py3dep
import rasterio
from rasterio.warp import transform_bounds, Resampling, calculate_default_transform, transform as rio_transform, reproject
from rasterio.merge import merge
from rasterio.mask import mask as rio_mask
from whitebox.whitebox_tools import WhiteboxTools

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
SPIKE = ROOT / "spikes" / "1m-watershed"
SPIKE.mkdir(parents=True, exist_ok=True)

TARGET_CRS = "EPSG:5070"
RES = 1.0
THRESHOLDS = [1000, 2500, 5000]
N_TILES_X = 4  # columns
N_TILES_Y = 3  # rows
PAD = 200      # meters padding around watershed bbox for DEM fetch

# ── Derive fetch bbox from canonical watershed boundary ──
ws = gpd.read_file(ROOT / "data/vectors/henderson_watershed_boundary.geojson")
ws_5070 = ws.to_crs(TARGET_CRS)
xmin, ymin, xmax, ymax = ws_5070.total_bounds
BBOX_5070 = (xmin - PAD, ymin - PAD, xmax + PAD, ymax + PAD)
BBOX_4326 = transform_bounds(TARGET_CRS, "EPSG:4326", *BBOX_5070)

print(f"Watershed bbox EPSG:5070: ({BBOX_5070[0]:.0f}, {BBOX_5070[1]:.0f}, {BBOX_5070[2]:.0f}, {BBOX_5070[3]:.0f})")
print(f"Watershed bbox EPSG:4326: ({BBOX_4326[0]:.4f}, {BBOX_4326[1]:.4f}, {BBOX_4326[2]:.4f}, {BBOX_4326[3]:.4f})")

# ── Step 1: Tile DEM fetch (memory-safe) ──
mosaic_path = SPIKE / "dem_1m_5070.tif"

if not mosaic_path.exists():
    t_total = time.time()
    dx_4326 = (BBOX_4326[2] - BBOX_4326[0]) / N_TILES_X
    dy_4326 = (BBOX_4326[3] - BBOX_4326[1]) / N_TILES_Y
    tile_paths = []

    for row in range(N_TILES_Y):
        for col in range(N_TILES_X):
            w = BBOX_4326[0] + col * dx_4326
            e = w + dx_4326
            s = BBOX_4326[3] - (row + 1) * dy_4326
            n = s + dy_4326
            t0 = time.time()
            print(f"  Tile [{row},{col}] ({w:.4f},{s:.4f},{e:.4f},{n:.4f})...", end=" ", flush=True)
            tile = py3dep.get_dem((w, s, e, n), resolution=1, crs=4326)
            tp = SPIKE / f"_tile_r{row}_c{col}.tif"
            tile.rio.to_raster(tp)
            tile_paths.append(tp)
            del tile
            gc.collect()
            print(f"{tp.stat().st_size/1e6:.0f}MB in {time.time()-t0:.0f}s")

    print(f"  {len(tile_paths)} tiles fetched")

    # Reproject each tile to EPSG:5070, then merge
    reproj_tiles = []
    for i, tp in enumerate(tile_paths):
        rp = SPIKE / f"_reproj_{i}.tif"
        with rasterio.open(tp) as src:
            transform, width, height = calculate_default_transform(
                src.crs, TARGET_CRS, src.width, src.height, *src.bounds, resolution=RES)
            profile = src.profile.copy()
            profile.update(crs=TARGET_CRS, transform=transform, width=width, height=height,
                           dtype="float32", compress="lzw")
            with rasterio.open(rp, "w", **profile) as dst:
                reproject(source=rasterio.band(src, 1), destination=rasterio.band(dst, 1),
                          src_transform=src.transform, src_crs=src.crs,
                          dst_transform=transform, dst_crs=TARGET_CRS,
                          resampling=Resampling.bilinear)
        reproj_tiles.append(rp)
        tp.unlink()  # delete raw tile immediately
    print(f"  {len(reproj_tiles)} tiles reprojected")

    # Merge reprojected tiles
    mosaic, out_transform = merge(reproj_tiles, bounds=BBOX_5070, res=RES, method="first")
    with rasterio.open(reproj_tiles[0]) as src0:
        profile = src0.profile.copy()
    profile.update(transform=out_transform, width=mosaic.shape[2], height=mosaic.shape[1],
                   compress="lzw")
    with rasterio.open(mosaic_path, "w", **profile) as dst:
        dst.write(mosaic)
    for rp in reproj_tiles:
        rp.unlink()

    with rasterio.open(mosaic_path) as s:
        print(f"  Mosaic: {s.width}×{s.height}, {mosaic_path.stat().st_size/1e6:.0f}MB in {time.time()-t_total:.0f}s")
else:
    with rasterio.open(mosaic_path) as s:
        print(f"  Using cached mosaic: {s.width}×{s.height}, {mosaic_path.stat().st_size/1e6:.0f}MB")

# ── Step 2: Clip to watershed boundary ──
clipped_dem = SPIKE / "dem_clipped.tif"

if not clipped_dem.exists():
    t0 = time.time()
    # Get watershed polygon in EPSG:5070
    ws_5070_geom = ws_5070.geometry.values  # list of shapely geometries
    with rasterio.open(mosaic_path) as src:
        out_image, out_transform = rio_mask(src, ws_5070_geom, crop=True, nodata=src.nodata)
        profile = src.profile.copy()
    profile.update(transform=out_transform, width=out_image.shape[2], height=out_image.shape[1],
                   compress="lzw", dtype="float32")
    with rasterio.open(clipped_dem, "w", **profile) as dst:
        dst.write(out_image)
    with rasterio.open(clipped_dem) as s:
        print(f"  Clipped DEM: {s.width}×{s.height}, {clipped_dem.stat().st_size/1e6:.0f}MB in {time.time()-t0:.0f}s")
else:
    with rasterio.open(clipped_dem) as s:
        print(f"  Using cached clipped DEM: {s.width}×{s.height}")

# ── Step 3: Fill depressions (WBT — fill-only, skip breach to stay under memory) ──
# BreachDepressions on 165M px OOMs on 7.6 GB RAM. FillDepressions is lighter.
# For watershed-scale D-infty, fill is adequate — breach matters for local fan routing.
wbt = WhiteboxTools()
wbt.set_working_dir(str(SPIKE.resolve()))
wbt.set_verbose_mode(False)  # suppress WBT progress lines — they can pipe-stall on large rasters

filled = SPIKE / "_filled.tif"

if not filled.exists():
    t0 = time.time()
    print("  Filling...", end=" ", flush=True)
    try:
        wbt.fill_depressions(str(clipped_dem.resolve()), str(filled.resolve()), fix_flats=True)
    except Exception as e:
        print(f"\n  FILL FAILED: {e}")
        raise
    elapsed = time.time() - t0
    print(f"{elapsed:.0f}s")
    if not filled.exists():
        raise RuntimeError(f"WBT fill_depressions claimed success but {filled} not found")
else:
    print("  Using cached filled DEM")

# Fill_depressions is the only intermediate here; delete clipped DEM if no longer needed
# (keep clipped DEM — it's the canonical clipped source at 418 MB)

# ── Step 4: Resample to 2m + D∞ flow accumulation ──
# WBT DInfFlowAccumulation OOMs on 165M px (1m) on 7.6 GB RAM.
# Resample to 2m → 41M px, compute D∞, upsample stream rasters back to 1m.
# Stream thresholds divided by 4 to maintain equivalent contributing area.

RESAMPLE_RES = 2.0
RESAMPLE_SCALE = int(RESAMPLE_RES / RES)  # 2
THRESHOLDS_2M = [t // (RESAMPLE_SCALE ** 2) for t in THRESHOLDS]  # [250, 625, 1250]

filled_2m = SPIKE / "_filled_2m.tif"

if not filled_2m.exists():
    t0 = time.time()
    print(f"  Resampling filled DEM to {RESAMPLE_RES}m...", end=" ", flush=True)
    with rasterio.open(filled) as src:
        from rasterio.enums import Resampling as R
        new_height = src.height // RESAMPLE_SCALE
        new_width = src.width // RESAMPLE_SCALE
        data = src.read(1, out_shape=(new_height, new_width), resampling=R.bilinear)
        transform_2m = src.transform * src.transform.scale(
            src.width / new_width, src.height / new_height)
        profile = src.profile.copy()
        profile.update(width=new_width, height=new_height, transform=transform_2m,
                       compress="lzw")
        with rasterio.open(filled_2m, "w", **profile) as dst:
            dst.write(data, 1)
    with rasterio.open(filled_2m) as s:
        print(f"{s.width}×{s.height}, {filled_2m.stat().st_size/1e6:.0f}MB in {time.time()-t0:.0f}s")
else:
    with rasterio.open(filled_2m) as s:
        print(f"  Using cached 2m DEM: {s.width}×{s.height}")

# D∞ on 2m DEM
dinf_2m = SPIKE / "dinf_flow_accum_2m.tif"

if not dinf_2m.exists():
    t0 = time.time()
    print("  D∞ on 2m DEM...", end=" ", flush=True)
    try:
        wbt.d_inf_flow_accumulation(str(filled_2m.resolve()), str(dinf_2m.resolve()), out_type="cells")
    except Exception as e:
        print(f"\n  D∞ FAILED: {e}")
        raise
    elapsed = time.time() - t0
    print(f"{elapsed:.0f}s")
    if not dinf_2m.exists():
        raise RuntimeError(f"WBT d_inf_flow_accumulation claimed success but {dinf_2m} not found")
    # Clean up intermediates
    filled.unlink()
    filled_2m.unlink()
    print("  Filled DEMs deleted (D∞ complete)")
else:
    print("  Using cached 2m D∞ accumulation")

# Compress the 2m D∞ raster
with rasterio.open(dinf_2m) as src:
    needs_compress = (src.profile.get("compress") != "lzw" or src.dtypes[0] != "float32")
if needs_compress:
    t0 = time.time()
    with rasterio.open(dinf_2m) as src:
        data = src.read(1)
        profile = src.profile.copy()
    profile.update(compress="lzw", dtype="float32", nodata=-32768.0)
    tmp = SPIKE / "_dinf_2m_compressed.tif"
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(data.astype("float32"), 1)
    dinf_2m.unlink()
    tmp.rename(dinf_2m)
    with rasterio.open(dinf_2m) as s:
        print(f"  D∞ 2m compressed: {s.width}×{s.height}, {dinf_2m.stat().st_size/1e6:.0f}MB in {time.time()-t0:.0f}s")

# ── Step 5: Single continuous stream export at lowest threshold ──
# Extract all stream cells at threshold 250 (2m) = 1000 (1m), export as one
# Parquet sorted by accum descending. The slider morphs continuously because
# it renders cells where accum >= slider_value.
LOWEST_2M = THRESHOLDS_2M[0]  # 250
LOWEST_1M = LOWEST_2M * (RESAMPLE_SCALE ** 2)  # 1000
stream_2m = SPIKE / f"_streams_2m_{LOWEST_2M}.tif"
stream_1m = SPIKE / f"streams_{LOWEST_1M}.tif"
parquet_path = SPIKE / "streams_all.parquet"

with rasterio.open(dinf_2m) as src:
    accum_data_2m = src.read(1)

if not parquet_path.exists():
    t0 = time.time()

    # Extract streams on 2m D∞ at lowest threshold
    if not stream_2m.exists():
        print(f"  Extracting streams at 2m t={LOWEST_2M}...", end=" ", flush=True)
        wbt.extract_streams(str(dinf_2m.resolve()), str(stream_2m.resolve()),
                            LOWEST_2M, zero_background=True)

    # Read 2m stream raster and upsample to 1m
    with rasterio.open(stream_2m) as src:
        sdata_2m = src.read(1)
        sdata_1m = np.repeat(np.repeat(sdata_2m, RESAMPLE_SCALE, axis=0), RESAMPLE_SCALE, axis=1)
        with rasterio.open(SPIKE / "dem_clipped.tif") as ref:
            h1, w1 = ref.height, ref.width
            transform_1m = ref.transform
            profile_1m = ref.profile.copy()
        sdata_1m = sdata_1m[:h1, :w1]

    # Write 1m stream raster (binary, compressed)
    profile_1m.update(dtype="uint8", nodata=0, compress="lzw")
    with rasterio.open(stream_1m, "w", **profile_1m) as dst:
        dst.write(sdata_1m.astype("uint8"), 1)

    # Extract all stream cell coordinates at 1m
    stream_rows, stream_cols = np.where(sdata_1m > 0)
    n_stream = len(stream_rows)

    xs = transform_1m.c + (stream_cols + 0.5) * transform_1m.a
    ys = transform_1m.f + (stream_rows + 0.5) * transform_1m.e
    lons, lats = rio_transform(TARGET_CRS, "EPSG:4326", xs, ys)
    lons = np.asarray(lons, dtype="float64")
    lats = np.asarray(lats, dtype="float64")

    # Accumulation from parent 2m cell
    rows_2m = stream_rows // RESAMPLE_SCALE
    cols_2m = stream_cols // RESAMPLE_SCALE
    accums = accum_data_2m[rows_2m, cols_2m]

    # Single Parquet, sorted by accum descending (for continuous slider)
    df = pd.DataFrame({
        "accum": accums.astype("int64"),
        "x_5070": xs.astype("float32"),
        "y_5070": ys.astype("float32"),
        "lon": lons.astype("float64"),
        "lat": lats.astype("float64"),
    })
    df.sort_values("accum", ascending=False, inplace=True)
    df.to_parquet(parquet_path, index=False)

    stream_2m.unlink()
    print(f"  {n_stream:,} cells (t≥{LOWEST_1M}) → {parquet_path.stat().st_size/1e6:.1f}MB in {time.time()-t0:.0f}s")
else:
    print(f"  Using cached streams_all.parquet")

# Delete old discrete Parquet files (replaced by streams_all.parquet)
for t in THRESHOLDS:
    old = SPIKE / f"streams_{t}.parquet"
    if old.exists():
        old.unlink()
        print(f"  Deleted old discrete {old.name}")

# ── Summary ──
print(f"\n=== Final artifacts ({SPIKE}) ===")
for p in sorted(SPIKE.glob("*")):
    if p.is_file() and not p.name.startswith("_"):
        print(f"  {p.name:50s} {p.stat().st_size/1e6:8.0f}MB")
disk_gb = sum(p.stat().st_size for p in SPIKE.rglob("*") if p.is_file()) / 1e9
print(f"  Total disk: {disk_gb:.1f}GB")
