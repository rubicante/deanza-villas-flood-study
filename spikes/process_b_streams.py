"""Process B: Stream extraction + uint8 conversion, rlimit 4 GB."""
import os, sys, time, resource, gc
import numpy as np
import rasterio
from pathlib import Path
from whitebox.whitebox_tools import WhiteboxTools

GB = 1024**3
resource.setrlimit(resource.RLIMIT_AS, (4 * GB, 4 * GB))

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
HENDERSON = ROOT / "data" / "derived" / "henderson"
ACCUM = HENDERSON / "d8_flow_accum_1m.tif"
STREAMS_OUT = HENDERSON / "streams_d8_1m_250.tif"

t0 = time.time()
print(f"Process B: stream extraction, OMP={os.environ.get('OMP_NUM_THREADS','?')}")

wbt = WhiteboxTools()
wbt.set_working_dir(str(HENDERSON))
wbt.set_verbose_mode(False)
wbt.extract_streams(str(ACCUM.resolve()), str(STREAMS_OUT.resolve()), 250, zero_background=True)

# Read back, convert to uint8, rewrite
with rasterio.open(STREAMS_OUT) as src:
    data = src.read(1)
    profile = src.profile
n_stream = int((data > 0).sum())
print(f"  Stream cells (t=250): {n_stream:,}")

# Convert to uint8
uint8_data = (data > 0).astype("uint8")
profile.update(dtype="uint8", compress="lzw", nodata=0, bigtiff="YES")
with rasterio.open(STREAMS_OUT, "w", **profile) as dst:
    dst.write(uint8_data, 1)

del data, uint8_data; gc.collect()

elapsed = time.time() - t0
rusage = resource.getrusage(resource.RUSAGE_SELF)
peak_mb = rusage.ru_maxrss / 1024
fsize = STREAMS_OUT.stat().st_size / 1e6
print(f"Process B done: {elapsed:.0f}s, peak RSS: {peak_mb:.0f} MB, file: {fsize:.1f} MB")
