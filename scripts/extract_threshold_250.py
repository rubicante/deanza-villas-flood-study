"""Re-extract at threshold 250 to extend the low end of the continuous slider."""
import json, os, subprocess
from pathlib import Path
import geopandas as gpd
import numpy as np
import rasterio
from rasterio.warp import transform

REPO = Path("/home/hermes/workspace/deanza-villas-flood-study")
TERRAIN = REPO / "data/processed/terrain/deanza_villas_2km_1m"
DEM = TERRAIN / "deanza_villas_2km_1m_dem_filled.tif"
D8_FLOW = TERRAIN / "deanza_villas_2km_1m_dem_d8_flow_accum.tif"
D8_PNTR = TERRAIN / "deanza_villas_2km_1m_dem_d8_pointer.tif"
DINF_FLOW = TERRAIN / "deanza_villas_2km_1m_dem_dinf_flow_accum.tif"
OUT = REPO / "outputs/maps"
WBT = str(REPO / ".venv/lib/python3.13/site-packages/whitebox/WBT/whitebox_tools")
THRESHOLD = 250

def run_wbt(args):
    subprocess.run([WBT] + args, check=True)

# ── D8 ──
print(f"=== D8 threshold {THRESHOLD} ===")
streams_tif = TERRAIN / f"_tmp_d8_s{THRESHOLD}.tif"
run_wbt(["--run=ExtractStreams", f"--dem={DEM}", f"--flow_accum={D8_FLOW}",
         f"--output={streams_tif}", f"--threshold={THRESHOLD}", "--zero_background=False"])

streams_shp = TERRAIN / f"_tmp_d8_s{THRESHOLD}.shp"
run_wbt(["--run=RasterStreamsToVector", f"--streams={streams_tif}",
         f"--d8_pntr={D8_PNTR}", f"--output={streams_shp}"])

gdf = gpd.read_file(streams_shp)
gdf.crs = "EPSG:5070"
print(f"  {len(gdf)} segments")

with rasterio.open(D8_FLOW) as src:
    flow_data = src.read(1)
    tagged = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty: continue
        lines = [geom] if geom.geom_type == 'LineString' else list(geom.geoms)
        for line in lines:
            n = max(2, int(line.length / 5))
            samples = []
            for i in range(n):
                frac = i / (n - 1) if n > 1 else 0
                pt = line.interpolate(frac, normalized=True)
                r, c = src.index(pt.x, pt.y)
                if 0 <= r < src.height and 0 <= c < src.width:
                    samples.append(flow_data[r, c])
            if not samples: continue
            min_accum = int(min(samples))
            coords = list(line.coords)
            if len(coords) < 2: continue
            xs = [c[0] for c in coords]; ys = [c[1] for c in coords]
            xs_g, ys_g = transform(src.crs, 'EPSG:4326', xs, ys)
            tagged.append({
                'type': 'Feature',
                'properties': {'min_accum': min_accum},
                'geometry': {'type': 'LineString',
                    'coordinates': [[float(x), float(y)] for x, y in zip(xs_g, ys_g)]}
            })

fc = {'type': 'FeatureCollection', 'features': tagged}
d8_out = OUT / 'threshold_continuous_d8.geojson'
with open(d8_out, 'w') as f: json.dump(fc, f)
accums = [f['properties']['min_accum'] for f in tagged]
print(f"  Wrote {len(tagged)} features ({os.path.getsize(d8_out)/1e6:.1f} MB)")
print(f"  Accum: {min(accums)}–{max(accums)}, median {np.median(accums):.0f}")

for pat in [f"_tmp_d8_s{THRESHOLD}"]:
    for ext in ['.tif','.shp','.shx','.dbf','.prj','.gpkg']:
        f = TERRAIN / (pat + ext)
        if f.exists(): f.unlink()

# ── D∞ ──
print(f"\n=== D∞ threshold {THRESHOLD} ===")
with rasterio.open(DINF_FLOW) as src:
    data = src.read(1)
    rows, cols = (data >= THRESHOLD).nonzero()
    values = data[rows, cols]
    print(f"  {len(values)} cells")
    xs_src, ys_src = src.xy(cols, rows)
    xs_g, ys_g = transform(src.crs, 'EPSG:4326', xs_src, ys_src)
    features = [{'type': 'Feature', 'properties': {'min_accum': int(v)},
                 'geometry': {'type': 'Point', 'coordinates': [float(x), float(y)]}}
                for v, x, y in zip(values, xs_g, ys_g)]

fc = {'type': 'FeatureCollection', 'features': features}
dinf_out = OUT / 'threshold_continuous_dinf.geojson'
with open(dinf_out, 'w') as f: json.dump(fc, f)
print(f"  Wrote {len(features)} features ({os.path.getsize(dinf_out)/1e6:.1f} MB)")
print(f"  Accum: {values.min()}–{values.max()}, median {np.median(values):.0f}")
print("\nDone.")
