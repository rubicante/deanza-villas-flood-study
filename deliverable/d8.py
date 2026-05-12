"""
D8 flow accumulation.

Backends:
    'wbt'                    — WBT d8_pointer + d8_flow_accumulation
    'pyflwdir'               — pyflwdir from_dem (refills internally)
    'wbt_ptr_pyflwdir'       — WBT pointer + pyflwdir accumulation (no refill)
    'auto' (default)         — try 'wbt', fall back to 'wbt_ptr_pyflwdir' on hang

Key spike lessons:
  - WBT pointer works at all raster sizes (14s on 165M px)
  - WBT d8_flow_accumulation hangs on this system (all sizes)
  - Mask pointer: nodata → 0 prevents accumulation cycles
  - pyflwdir.from_array(ptr, ftype='d8', check_ftype=False) — no refill
  - upstream_area(unit='cell') for cell counts
"""

from pathlib import Path
import time
import numpy as np
import rasterio
from whitebox.whitebox_tools import WhiteboxTools


# WBT → pyflwdir D8 encoding translation (powers-of-2 LUT)
# WBT:     1=NE, 2=E, 4=SE, 8=S, 16=SW, 32=W, 64=NW, 128=N  (clockwise from NE)
# pyflwdir: 1=E, 2=SE, 4=S, 8=SW, 16=W, 32=NW, 64=N, 128=NE (clockwise from E)
_WBT_TO_PYFLWDIR = np.zeros(256, dtype="uint8")
_WBT_TO_PYFLWDIR[1] = 128   # NE → NE
_WBT_TO_PYFLWDIR[2] = 1     # E  → E
_WBT_TO_PYFLWDIR[4] = 2     # SE → SE
_WBT_TO_PYFLWDIR[8] = 4     # S  → S
_WBT_TO_PYFLWDIR[16] = 8    # SW → SW
_WBT_TO_PYFLWDIR[32] = 16   # W  → W
_WBT_TO_PYFLWDIR[64] = 32   # NW → NW
_WBT_TO_PYFLWDIR[128] = 64  # N  → N


def compute_d8_pointer(
    dem: Path,
    output: Path = Path("d8_pointer.tif"),
) -> Path:
    """WBT d8_pointer. Returns output Path."""
    dem = Path(dem).resolve()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    wbt = WhiteboxTools()
    wbt.set_working_dir(str(output.parent))
    wbt.set_verbose_mode(False)

    t0 = time.time()
    wbt.d8_pointer(str(dem), str(output))
    if not output.exists():
        raise RuntimeError(f"WBT d8_pointer failed: {output} not found")
    print(f"  D8 pointer: {time.time()-t0:.0f}s → {output}")
    return output


def compute_d8_accum(
    dem: Path,
    output: Path = Path("d8_flow_accum.tif"),
    pointer: Path | None = None,
    backend: str = "auto",
    watershed_geom: Path | None = None,
) -> Path:
    """
    D8 flow accumulation. Returns output Path.

    backend:
        'wbt' — WBT d8_flow_accumulation
        'pyflwdir' — pyflwdir from_dem
        'wbt_ptr_pyflwdir' — WBT pointer + pyflwdir accumulation (no refill)
        'auto' — try wbt, fall back to wbt_ptr_pyflwdir

    watershed_geom : Path or None
        GeoJSON polygon to mask accumulation to. Required for >100M-cell grids
        where pyflwdir full-graph arrays would OOM. Only used with
        wbt_ptr_pyflwdir backend. Non-watershed cells get accum=0.
    """
    dem = Path(dem).resolve()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    backends = {"wbt", "pyflwdir", "wbt_ptr_pyflwdir", "auto"}
    if backend not in backends:
        raise ValueError(f"Unknown backend '{backend}'. Choose from {backends}")

    wbt = WhiteboxTools()
    wbt.set_working_dir(str(output.parent))
    wbt.set_verbose_mode(False)

    # --- WBT native ---
    if backend == "wbt":
        ptr = pointer or compute_d8_pointer(dem, output.parent / f"_{output.stem}_ptr.tif")
        ptr = Path(ptr).resolve()
        t0 = time.time()
        wbt.d8_flow_accumulation(str(dem), str(output), out_type="cells", pntr=str(ptr))
        if not output.exists():
            raise RuntimeError(f"WBT d8_flow_accumulation failed: {output} not found")
        print(f"  D8 accum (wbt): {time.time()-t0:.0f}s → {output}")
        return output

    # --- pyflwdir from_dem (refills internally) ---
    if backend == "pyflwdir":
        import pyflwdir
        with rasterio.open(dem) as src:
            dem_data = src.read(1)
            transform = src.transform
            nodata_val = src.nodata
            profile = src.profile

        valid_mask = np.ones(dem_data.shape, dtype=bool)
        if nodata_val is not None:
            valid_mask = dem_data != nodata_val

        t0 = time.time()
        flw = pyflwdir.from_dem(
            np.where(valid_mask, dem_data, np.nan),
            nodata=np.nan, max_depth=1e6, transform=transform)
        accum = flw.upstream_area(unit='cell')
        print(f"  D8 accum (pyflwdir): {time.time()-t0:.0f}s")

        accum_full = np.zeros_like(dem_data, dtype="float32")
        accum_full[valid_mask] = accum.ravel()

        profile.update(dtype="float32", compress="lzw", nodata=0.0)
        with rasterio.open(output, "w", **profile) as dst:
            dst.write(accum_full, 1)
        print(f"  → {output}")
        return output

    # --- WBT pointer + pyflwdir accumulation ---
    if backend in ("wbt_ptr_pyflwdir", "auto"):
        ptr = pointer or compute_d8_pointer(dem, output.parent / f"_{output.stem}_ptr.tif")
        ptr = Path(ptr).resolve()

        # If auto: try WBT first
        if backend == "auto":
            try:
                wbt_accum = output.parent / f"_{output.stem}_wbt.tif"
                t0 = time.time()
                wbt.d8_flow_accumulation(str(dem), str(wbt_accum),
                                          out_type="cells", pntr=str(ptr))
                if wbt_accum.exists():
                    print(f"  D8 accum (auto→wbt): {time.time()-t0:.0f}s")
                    wbt_accum.rename(output)
                    return output
            except Exception:
                pass  # fall through to pyflwdir path

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
            import geopandas as gpd
            ws_gdf = gpd.read_file(watershed_geom)
            ws_gdf = ws_gdf.to_crs(ptr_profile["crs"])
            ws_mask = rasterio.features.rasterize(
                [(ws_gdf.geometry.iloc[0], 1)],
                out_shape=ptr_data.shape,
                transform=ptr_profile["transform"],
                dtype="uint8",
            )
            ptr_data[ws_mask == 0] = 0
            # Update valid_mask to match
            valid_mask = valid_mask & (ws_mask > 0)
            del ws_gdf, ws_mask

        # Translate WBT D8 encoding → pyflwdir D8 encoding
        ptr_data = _WBT_TO_PYFLWDIR[ptr_data]

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
