"""
D-infinity flow accumulation via WBT.

Key spike lessons:
  - out_type="cells" MUST be explicit — D∞ defaults to SCA which produces inf
  - WBT D∞ internally upcasts to float64 (memory-hungry on large rasters)
  - No memory guard — let WBT fail and surface the OSError
"""

from pathlib import Path
import time
import rasterio
from whitebox.whitebox_tools import WhiteboxTools


def compute_dinf(
    dem: Path,
    output: Path = Path("dinf_flow_accum.tif"),
) -> Path:
    """
    WBT d_inf_flow_accumulation with out_type="cells".
    Returns output Path. Raises on failure.
    """
    dem = Path(dem).resolve()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    wbt = WhiteboxTools()
    wbt.set_working_dir(str(output.parent))
    wbt.set_verbose_mode(False)

    t0 = time.time()
    wbt.d_inf_flow_accumulation(str(dem), str(output), out_type="cells")
    if not output.exists():
        raise RuntimeError(f"WBT d_inf_flow_accumulation failed: {output} not found")
    print(f"  D∞: {time.time()-t0:.0f}s → {output}")

    # Compress (WBT writes uncompressed)
    with rasterio.open(output) as src:
        data = src.read(1)
        prof = src.profile.copy()
    prof.update(compress="lzw", dtype="float32", nodata=-32768.0)
    tmp = output.parent / f"_{output.stem}_compressed.tif"
    with rasterio.open(tmp, "w", **prof) as dst:
        dst.write(data.astype("float32"), 1)
    output.unlink()
    tmp.rename(output)
    print(f"    compressed: {output.stat().st_size/1e6:.0f}MB")
    return output
