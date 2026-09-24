"""
DEM preprocessing: breach depressions and/or fill.

Key spike lessons:
  - All WBT paths must be absolute (silent failure with relative paths)
  - breach_then_fill is correct for alluvial fans (fill-only creates flats)
  - Verify no NaN in output
  - WBT writes float64 by default → caller should fetch float32 first
  - WBT 2.3.6 FillDepressions intermittently panics (exit 101); floodflow.wbt
    checks exit codes and retries panics

Strategies:
    'fill_only'         — fill_depressions only
    'breach_only'       — breach_depressions only
    'breach_then_fill'  — breach → fill (default)
"""

from pathlib import Path

import numpy as np
import rasterio

from floodflow import wbt


def preprocess_dem(
    dem: Path,
    output: Path = Path("preprocessed.tif"),
    strategy: str = "breach_then_fill",
    breach_max_length: int = 250,
    fix_flats: bool = True,
) -> Path:
    """
    Breach and/or fill a DEM. Returns output Path.

    strategy: 'fill_only', 'breach_only', 'breach_then_fill'
    breach_max_length: max breach channel length in cells (ignored for fill_only)
    fix_flats: passed to fill_depressions (ignored for breach_only)
    """
    dem = Path(dem).resolve()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    strategies = {"fill_only", "breach_only", "breach_then_fill"}
    if strategy not in strategies:
        raise ValueError(f"Unknown strategy '{strategy}'. Choose from {strategies}")

    current = dem

    if strategy in ("breach_only", "breach_then_fill"):
        breached = output.parent / f"_{output.stem}_breached.tif"
        # Snapshot pre-breach for diagnostics
        with rasterio.open(current) as src:
            pre_data = src.read(1)
            nodata = src.profile.get("nodata", -32768)
        wbt.run("BreachDepressions", breached, dem=current, max_length=breach_max_length)
        # Log breach diagnostics. BreachDepressions also fills what it cannot
        # breach, so cells can move up (fill) as well as down (cut).
        with rasterio.open(breached) as src:
            post_data = src.read(1)
        valid = (pre_data != nodata) & (post_data != nodata)
        diff = pre_data[valid] - post_data[valid]
        n_changed = int(np.count_nonzero(diff))
        if n_changed > 0:
            print(f"  Breached: {n_changed:,} cells modified, "
                  f"max cut {float(diff.max()):.2f}m, max fill {float(-diff.min()):.2f}m, "
                  f"net {float(diff.sum())/1e6:+.2f}M m³ (+ = removed)")
        else:
            print("  Breached: 0 cells modified (no depressions)")
        current = breached

    if strategy in ("fill_only", "breach_then_fill"):
        wbt.run("FillDepressions", output, dem=current, fix_flats=fix_flats)
        if current != dem:
            current.unlink()  # intermediate breached DEM
    else:  # breach_only
        current.rename(output)

    # Verify: no NaN
    with rasterio.open(output) as src:
        data = src.read(1)
        n_nan = np.sum(np.isnan(data))
        if n_nan > 0:
            raise RuntimeError(f"{n_nan} NaN cells in output")

    print(f"  Preprocessed ({strategy}): {output}")
    return output
