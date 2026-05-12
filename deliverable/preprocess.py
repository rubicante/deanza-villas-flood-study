"""
DEM preprocessing: breach depressions and/or fill.

Key spike lessons:
  - All WBT paths must be absolute (silent failure with relative paths)
  - breach_then_fill is correct for alluvial fans (fill-only creates flats)
  - Verify no NaN in output
  - WBT writes float64 by default → caller should fetch float32 first

Strategies:
    'fill_only'         — fill_depressions only
    'breach_only'       — breach_depressions only
    'breach_then_fill'  — breach → fill (default)
"""

from pathlib import Path
import numpy as np
import rasterio
from whitebox.whitebox_tools import WhiteboxTools


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

    wbt = WhiteboxTools()
    wbt.set_working_dir(str(output.parent))
    wbt.set_verbose_mode(False)

    current = dem
    work_dir = output.parent

    if strategy in ("breach_only", "breach_then_fill"):
        breached = work_dir / f"_{output.stem}_breached.tif"
        # Snapshot pre-breach for diagnostics
        with rasterio.open(current) as src:
            pre_data = src.read(1)
            pre_profile = src.profile
        wbt.breach_depressions(str(current), str(breached), max_length=breach_max_length)
        if not breached.exists():
            raise RuntimeError(f"WBT breach_depressions failed: {breached} not found")
        # Log breach diagnostics
        with rasterio.open(breached) as src:
            post_data = src.read(1)
        valid = (pre_data != pre_profile.get("nodata", -32768)) & (post_data != pre_profile.get("nodata", -32768))
        n_changed = int(np.sum(valid & (pre_data != post_data)))
        if n_changed > 0:
            diff = pre_data[valid] - post_data[valid]
            max_cut = float(np.max(diff))
            total_volume = float(np.sum(diff))
            print(f"  Breached: {n_changed:,} cells modified, "
                  f"max cut {max_cut:.2f}m, "
                  f"{total_volume/1e6:.2f}M m³ removed")
        else:
            print("  Breached: 0 cells modified (no depressions)")
        current = breached

    if strategy in ("fill_only", "breach_then_fill"):
        if strategy == "breach_then_fill":
            filled_out = output  # write final output directly
        else:
            filled_out = output
        wbt.fill_depressions(str(current), str(filled_out), fix_flats=fix_flats)
        if not filled_out.exists():
            raise RuntimeError(f"WBT fill_depressions failed: {filled_out} not found")
        current = filled_out

    if strategy == "breach_only":
        # Move breached to output
        current.rename(output)
        current = output

    # Verify: no NaN
    with rasterio.open(output) as src:
        data = src.read(1)
        n_nan = np.sum(np.isnan(data))
        if n_nan > 0:
            raise RuntimeError(f"{n_nan} NaN cells in output")

    print(f"  Preprocessed ({strategy}): {output}")
    return output
