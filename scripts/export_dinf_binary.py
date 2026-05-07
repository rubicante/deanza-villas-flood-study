"""Export D∞ flow accumulation as compact sorted binary for fast browser loading."""
import struct
from pathlib import Path
import numpy as np
import rasterio
from rasterio.warp import transform

REPO = Path("/home/hermes/workspace/deanza-villas-flood-study")
DINF_FLOW = REPO / "data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_dinf_flow_accum.tif"
OUT = REPO / "outputs/maps/threshold_dinf_sorted.bin"

ACCUM_MIN = 250

print("Reading D∞ flow accumulation raster...")
with rasterio.open(DINF_FLOW) as src:
    data = src.read(1)
    rows, cols = (data >= ACCUM_MIN).nonzero()
    values = data[rows, cols]
    print(f"  {len(values)} cells with accum >= {ACCUM_MIN}")

    # Convert to lat/lon
    xs_src, ys_src = src.xy(cols, rows)
    lons, lats = transform(src.crs, 'EPSG:4326', xs_src, ys_src)
    lons = np.array(lons)
    lats = np.array(lats)

# Sort by accum descending
order = np.argsort(values)[::-1]
values = values[order]
lons = lons[order]
lats = lats[order]

# Write as flat float32 triples: [accum, lon, lat]
buf = np.empty(len(values) * 3, dtype=np.float32)
buf[0::3] = values.astype(np.float32)
buf[1::3] = lons.astype(np.float32)
buf[2::3] = lats.astype(np.float32)

with open(OUT, 'wb') as f:
    f.write(struct.pack('<I', len(values)))  # count as uint32 header
    f.write(buf.tobytes())

size_mb = OUT.stat().st_size / 1e6
print(f"  Wrote {len(values)} cells ({size_mb:.1f} MB) to {OUT}")
print(f"  Accum range: {values[-1]:.0f} – {values[0]:.0f}")
print("Done.")
