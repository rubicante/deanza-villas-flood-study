"""Spike: Delineate contributing watershed for the De Anza community bbox.
Uses existing Henderson 10m DEM. Computes D8 pointer, watershed, masks D∞,
exports binary. All in spikes/henderson-canyon/.
"""
from pathlib import Path
import struct, time, json

import geopandas as gpd
import numpy as np
import rasterio
from rasterio import features
from rasterio.warp import transform_bounds
from whitebox.whitebox_tools import WhiteboxTools

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
SPIKE = ROOT / "spikes" / "henderson-canyon"

# Existing artifacts from Henderson spike
DEM_FILLED = SPIKE / "dem_filled_breached.tif"
DINF_ACCUM = SPIKE / "dinf_flow_accum.tif"
COMMUNITY_GEOJSON = ROOT / "outputs" / "maps" / "deanza_community_poi.geojson"

TARGET_CRS = "EPSG:5070"

print("=== Step 1: Load community bbox, rasterize to pour points ===")
# Read community GeoJSON
community = gpd.read_file(COMMUNITY_GEOJSON)
# Reproject to match DEM CRS
with rasterio.open(DEM_FILLED) as src:
    dem_crs = src.crs
    dem_transform = src.transform
    dem_shape = src.shape
    print(f"  DEM: {dem_shape}, CRS={dem_crs}")

community_5070 = community.to_crs(dem_crs)
geom = community_5070.geometry.iloc[0]

# Rasterize: 1 = pour point, 0 = background
pour_raster = SPIKE / "pour_points.tif"
profile = {"driver": "GTiff", "count": 1, "height": dem_shape[0], "width": dem_shape[1],
           "transform": dem_transform, "crs": dem_crs, "dtype": "uint8", "compress": "lzw"}

if not pour_raster.exists():
    shapes = [(geom, 1)]
    mask = features.rasterize(shapes, out_shape=dem_shape, transform=dem_transform, dtype="uint8")
    with rasterio.open(pour_raster, "w", **profile) as dst:
        dst.write(mask, 1)
    print(f"  Pour points: {mask.sum()} cells in community bbox")

print("\n=== Step 2: D8 pointer (needed for watershed) ===")
wbt = WhiteboxTools()
wbt.set_working_dir(str(SPIKE))
wbt.set_verbose_mode(False)

d8_ptr = SPIKE / "d8_pointer.tif"
if not d8_ptr.exists():
    t0 = time.time()
    wbt.d8_pointer(str(DEM_FILLED), str(d8_ptr))
    print(f"  D8 pointer done in {time.time()-t0:.0f}s")

print("\n=== Step 3: Delineate watershed (skip snap — use pour points directly) ===")
watershed_rast = SPIKE / "watershed.tif"
if not watershed_rast.exists():
    t0 = time.time()
    wbt.watershed(str(d8_ptr), str(pour_raster), str(watershed_rast))
    with rasterio.open(watershed_rast) as s:
        cells = int((s.read(1) > 0).sum())
    print(f"  Watershed: {cells:,} cells ({cells * 100 / 1e6:.1f} km²) in {time.time()-t0:.0f}s")

print("\n=== Step 4: Mask D∞ accumulation to watershed ===")
masked_accum = SPIKE / "dinf_accum_watershed.tif"
if not masked_accum.exists():
    t0 = time.time()
    with rasterio.open(watershed_rast) as ws:
        ws_data = ws.read(1)
    with rasterio.open(DINF_ACCUM) as da:
        da_data = da.read(1)
        da_profile = da.profile.copy()
    masked = np.where(ws_data > 0, da_data, 0).astype(da_profile["dtype"])
    da_profile.update(compress="lzw")
    with rasterio.open(masked_accum, "w", **da_profile) as dst:
        dst.write(masked, 1)
    print(f"  Masked D∞ in {time.time()-t0:.0f}s")

print("\n=== Step 5: Extract streams at threshold 100, export binary ===")
streams_100 = SPIKE / "streams_watershed_100.tif"
if not streams_100.exists():
    wbt.extract_streams(str(masked_accum), str(streams_100), 100, zero_background=True)

binary_path = SPIKE / "threshold_dinf_watershed.bin"
if not binary_path.exists():
    t0 = time.time()
    with rasterio.open(streams_100) as src:
        sdata = src.read(1)
        transform_s = src.transform
    with rasterio.open(masked_accum) as src:
        accum_data = src.read(1)

    rows, cols = np.where(sdata > 0)
    print(f"  Stream cells at t=100 in watershed: {len(rows):,}")

    xs = transform_s.c + (cols + 0.5) * transform_s.a
    ys = transform_s.f + (rows + 0.5) * transform_s.e
    from rasterio.warp import transform as rio_transform
    lons, lats = rio_transform(dem_crs, "EPSG:4326", xs, ys)

    triples = list(zip(accum_data[rows, cols], lons, lats))
    triples.sort(key=lambda t: t[0], reverse=True)

    with open(binary_path, "wb") as f:
        f.write(struct.pack("I", len(triples)))
        for accum, lon, lat in triples:
            f.write(struct.pack("fff", float(accum), float(lon), float(lat)))
    print(f"  Binary: {len(triples):,} cells, {binary_path.stat().st_size/1e6:.1f}MB in {time.time()-t0:.0f}s")

print(f"\n=== Done ===")
print(f"Community watershed: see {watershed_rast}")
print(f"Binary: {binary_path}")
