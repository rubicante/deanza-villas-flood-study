"""
D8 flow accumulation.

Backends:
    'wbt_ptr_pyflwdir' (default) — WBT pointer + pyflwdir accumulation (no refill)
    'wbt'                        — WBT d8_pointer + d8_flow_accumulation. Hangs on
                                   WBT 2.3.6; kept only to retest after a WBT upgrade.

Removed: 'pyflwdir' (from_dem refills depressions, ~3.37× D∞ accumulation) and
'auto' (tried the hanging WBT call first, so it never fell back).

Key spike lessons:
  - WBT pointer works at all raster sizes (14s on 165M px)
  - WBT d8_flow_accumulation hangs on this system (all sizes)
  - Mask pointer: nodata → 0 prevents accumulation cycles
  - pyflwdir.from_array(ptr, ftype='d8', check_ftype=False) — no refill
  - upstream_area(unit='cell') for cell counts
"""

import time
from pathlib import Path

import numpy as np
import rasterio

from floodflow import wbt
from floodflow.encoding import WBT_TO_PYFLWDIR
from floodflow.geo import polygon_mask


def compute_d8_pointer(
    dem: Path,
    output: Path = Path("d8_pointer.tif"),
) -> Path:
    """WBT d8_pointer. Returns output Path."""
    dem = Path(dem).resolve()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    wbt.run("D8Pointer", output, dem=dem)
    print(f"  D8 pointer: {time.time()-t0:.0f}s → {output}")
    return output


def compute_d8_accum(
    dem: Path,
    output: Path = Path("d8_flow_accum.tif"),
    pointer: Path | None = None,
    backend: str = "wbt_ptr_pyflwdir",
    watershed_geom: Path | None = None,
) -> Path:
    """
    D8 flow accumulation. Returns output Path.

    backend:
        'wbt_ptr_pyflwdir' — WBT pointer + pyflwdir accumulation (no refill)
        'wbt' — WBT d8_flow_accumulation (hangs on WBT 2.3.6; retest only)

    watershed_geom : Path or None
        GeoJSON polygon to mask accumulation to. Required for >100M-cell grids
        where pyflwdir full-graph arrays would OOM. Only used with
        wbt_ptr_pyflwdir backend. Non-watershed cells get accum=0.
    """
    dem = Path(dem).resolve()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    backends = {"wbt", "wbt_ptr_pyflwdir"}
    if backend not in backends:
        raise ValueError(f"Unknown backend '{backend}'. Choose from {backends}")

    # --- WBT native ---
    if backend == "wbt":
        ptr = pointer or compute_d8_pointer(dem, output.parent / f"_{output.stem}_ptr.tif")
        ptr = Path(ptr).resolve()
        t0 = time.time()
        # --input is the pointer and --pntr says so (the old wrapper call
        # passed the DEM as input with a truthy pntr, i.e. DEM-as-pointer).
        wbt.run("D8FlowAccumulation", output, input=ptr, out_type="cells", pntr=True)
        print(f"  D8 accum (wbt): {time.time()-t0:.0f}s → {output}")
        return output

    # --- WBT pointer + pyflwdir accumulation ---
    if backend == "wbt_ptr_pyflwdir":
        ptr = pointer or compute_d8_pointer(dem, output.parent / f"_{output.stem}_ptr.tif")
        ptr = Path(ptr).resolve()

        # Load DEM for mask and transform
        with rasterio.open(dem) as src:
            dem_data = src.read(1)
            transform = src.transform
            nodata_val = src.nodata
            profile = src.profile

        valid_mask = np.ones(dem_data.shape, dtype=bool)
        if nodata_val is not None:
            valid_mask = dem_data != nodata_val

        # Load pointer, mask nodata → 0
        with rasterio.open(ptr) as src:
            ptr_data = src.read(1).astype('uint8')
            ptr_profile = src.profile.copy()
        ptr_data[~valid_mask] = 0

        # If watershed_geom provided, mask pointer to watershed
        if watershed_geom is not None:
            ws_mask = polygon_mask(watershed_geom, ptr_profile["crs"],
                                   ptr_profile["transform"], ptr_data.shape)
            ptr_data[ws_mask == 0] = 0
            # Update valid_mask to match
            valid_mask = valid_mask & (ws_mask > 0)
            del ws_mask

        # Translate WBT D8 encoding → pyflwdir D8 encoding
        ptr_data = WBT_TO_PYFLWDIR[ptr_data]

        # pyflwdir from pre-computed pointer (no refill)
        import pyflwdir
        t0 = time.time()
        flw = pyflwdir.from_array(ptr_data, ftype='d8', mask=valid_mask,
                                  transform=transform, check_ftype=False)
        accum = flw.upstream_area(unit='cell')
        print(f"  D8 accum (wbt_ptr_pyflwdir): {time.time()-t0:.0f}s")

        accum_full = np.where(valid_mask, accum, 0.0).astype("float32")

        profile.update(dtype="float32", compress="lzw", nodata=0.0)
        with rasterio.open(output, "w", **profile) as dst:
            dst.write(accum_full, 1)
        print(f"  → {output}")
        return output

    raise RuntimeError(f"Unreachable: backend={backend}")
