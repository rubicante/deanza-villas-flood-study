"""
Extract D8 and D-infinity stream networks at threshold 500,
tag each feature with exact flow accumulation value,
and write continuous-range GeoJSON files for the threshold explorer.

Recomputes D-infinity flow accumulation on the current (corrected) DEM.
"""
import json
import os
import subprocess
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.warp import transform
from shapely.geometry import LineString

REPO = Path("/home/hermes/workspace/deanza-villas-flood-study")
TERRAIN = REPO / "data/processed/terrain/deanza_villas_2km_1m"
DEM = TERRAIN / "deanza_villas_2km_1m_dem_filled.tif"
D8_FLOW = TERRAIN / "deanza_villas_2km_1m_dem_d8_flow_accum.tif"
D8_PNTR = TERRAIN / "deanza_villas_2km_1m_dem_d8_pointer.tif"
OUT = REPO / "outputs/maps"
WBT = str(REPO / ".venv/lib/python3.13/site-packages/whitebox/WBT/whitebox_tools")

THRESHOLD = 500

def run_wbt(args):
    cmd = [WBT] + args
    label = ' '.join(args[:3])
    print(f"  WBT: {label}...")
    subprocess.run(cmd, check=True)

# ═══════════════════════════════════════════════════════════
# D8: extract streams at 500, vectorize, sample flow accum
# ═══════════════════════════════════════════════════════════

print("=== D8: extracting streams at threshold", THRESHOLD)

streams_tif = TERRAIN / f"_tmp_d8_streams_{THRESHOLD}.tif"
run_wbt(["--run=ExtractStreams",
         f"--dem={DEM}", f"--flow_accum={D8_FLOW}",
         f"--output={streams_tif}", f"--threshold={THRESHOLD}",
         "--zero_background=False"])

streams_shp = TERRAIN / f"_tmp_d8_streams_{THRESHOLD}.shp"
run_wbt(["--run=RasterStreamsToVector",
         f"--streams={streams_tif}", f"--d8_pntr={D8_PNTR}",
         f"--output={streams_shp}"])

# WBT doesn't set CRS on shapefiles — set it manually
gdf = gpd.read_file(streams_shp)
gdf.crs = "EPSG:5070"
print(f"  Loaded {len(gdf)} stream segments")

with rasterio.open(D8_FLOW) as src:
    flow_data = src.read(1)
    tagged = []

    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        lines = [geom] if geom.geom_type == 'LineString' else list(geom.geoms)
        for line in lines:
            length = line.length
            n = max(2, int(length / 5))
            samples = []
            for i in range(n):
                frac = i / (n - 1) if n > 1 else 0
                pt = line.interpolate(frac, normalized=True)
                r, c = src.index(pt.x, pt.y)
                if 0 <= r < src.height and 0 <= c < src.width:
                    samples.append(flow_data[r, c])
            if not samples:
                continue

            min_accum = int(min(samples))
            coords = list(line.coords)
            if len(coords) < 2:
                continue

            xs = [c[0] for c in coords]
            ys = [c[1] for c in coords]
            xs_g, ys_g = transform(src.crs, 'EPSG:4326', xs, ys)
            geo_coords = [[float(x), float(y)] for x, y in zip(xs_g, ys_g)]

            tagged.append({
                'type': 'Feature',
                'properties': {'min_accum': min_accum},
                'geometry': {'type': 'LineString', 'coordinates': geo_coords}
            })

fc = {'type': 'FeatureCollection', 'features': tagged}
d8_out = OUT / 'threshold_continuous_d8.geojson'
with open(d8_out, 'w') as f:
    json.dump(fc, f)

accums = [f['properties']['min_accum'] for f in tagged]
print(f"  Wrote {len(tagged)} features ({os.path.getsize(d8_out)/1e6:.1f} MB)")
print(f"  Accum: {min(accums)}–{max(accums)}, median {np.median(accums):.0f}")

# Cleanup D8 temps
for pat in [f"_tmp_d8_streams_{THRESHOLD}"]:
    for ext in ['.tif', '.shp', '.shx', '.dbf', '.prj', '.gpkg']:
        f = TERRAIN / (pat + ext)
        if f.exists():
            f.unlink()

# ═══════════════════════════════════════════════════════════
# D∞: compute flow accumulation on correct DEM, extract cells
# ═══════════════════════════════════════════════════════════

print("\n=== D∞: computing flow accumulation")

dinf_flow = TERRAIN / "deanza_villas_2km_1m_dem_dinf_flow_accum.tif"

recompute = True
if dinf_flow.exists():
    with rasterio.open(dinf_flow) as s:
        if s.width == 1735 and s.height == 1722:
            print(f"  Already correct size ({s.width}x{s.height}), skipping")
            recompute = False

if recompute:
    run_wbt(["--run=DInfFlowAccumulation",
             f"--dem={DEM}", f"--output={dinf_flow}",
             "--out_type=cells"])

print(f"  Extracting D∞ cells with accum >= {THRESHOLD}")

with rasterio.open(dinf_flow) as src:
    data = src.read(1)
    rows, cols = (data >= THRESHOLD).nonzero()
    values = data[rows, cols]
    print(f"  {len(values)} cells found")

    xs_src, ys_src = src.xy(cols, rows)
    xs_g, ys_g = transform(src.crs, 'EPSG:4326', xs_src, ys_src)

    features = []
    for i in range(len(values)):
        features.append({
            'type': 'Feature',
            'properties': {'min_accum': int(values[i])},
            'geometry': {'type': 'Point', 'coordinates': [float(xs_g[i]), float(ys_g[i])]}
        })

fc = {'type': 'FeatureCollection', 'features': features}
dinf_out = OUT / 'threshold_continuous_dinf.geojson'
with open(dinf_out, 'w') as f:
    json.dump(fc, f)

print(f"  Wrote {len(features)} features ({os.path.getsize(dinf_out)/1e6:.1f} MB)")
print(f"  Accum: {values.min()}–{values.max()}, median {np.median(values):.0f}")

print("\nDone.")
