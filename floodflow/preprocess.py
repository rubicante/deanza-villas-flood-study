"""
DEM preprocessing: breach depressions and/or fill.

Key spike lessons:
  - All WBT paths must be absolute (silent failure with relative paths)
  - breach_then_fill is correct for alluvial fans (fill-only creates flats)
  - Verify no NaN in output
  - WBT writes float64 by default → caller should fetch float32 first
  - WBT 2.3.6 FillDepressions intermittently panics (fill_depressions.rs:368,
    exit 101, ~1–6% of runs on identical input), and the whitebox wrapper
    ignores exit codes, so it looks like success with no output. WBT is
    deterministic, so a missing output is retried (_run_until_output).

Strategies:
    'fill_only'         — fill_depressions only
    'breach_only'       — breach_depressions only
    'breach_then_fill'  — breach → fill (default)
"""

from pathlib import Path

import numpy as np
import rasterio
from whitebox.whitebox_tools import WhiteboxTools

_WBT_ATTEMPTS = 3


def _run_until_output(run, output: Path, tool: str) -> None:
    """Call a WBT tool until it writes `output` (see module docstring)."""
    for attempt in range(1, _WBT_ATTEMPTS + 1):
        run()
        if output.exists():
            return
        print(f"  WARNING: WBT {tool} wrote no output (attempt {attempt}/{_WBT_ATTEMPTS})")
    raise RuntimeError(f"WBT {tool} failed: {output} not found after {_WBT_ATTEMPTS} attempts")


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
        _run_until_output(
            lambda: wbt.breach_depressions(str(current), str(breached), max_length=breach_max_length),
            breached, "breach_depressions")
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
        _run_until_output(
            lambda: wbt.fill_depressions(str(current), str(output), fix_flats=fix_flats),
            output, "fill_depressions")
        current = output

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
