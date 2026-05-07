"""
Verification functions for flow accumulation rasters.

Key spike lessons:
  - nonzero_min == 1 catches SCA default on D∞ (nonzero_min would be cell width)
  - isfinite(max) BEFORE trusting max (inf renders max meaningless)
  - D8/D∞ agreement assumes single-outlet watershed
"""

from pathlib import Path
import numpy as np
import rasterio


def verify_accumulation(
    accum: Path,
    expected_dtype: str = "float32",
) -> dict:
    """
    Verify flow accumulation raster. Returns dict of stats.
    Checks: nonzero_min == 1, max is finite, zero inf, zero NaN.
    Raises AssertionError on failure.
    """
    with rasterio.open(accum) as src:
        data = src.read(1)
        nodata = src.nodata

    valid = data[data > 0] if nodata is None else data[(data != nodata) & (data > 0)]
    n_inf = int(np.sum(np.isinf(data)))
    n_nan = int(np.sum(np.isnan(data)))

    if len(valid) == 0:
        raise AssertionError("No positive accumulation values")

    max_val = np.max(valid)

    assert np.isfinite(max_val), \
        f"max is not finite: {max_val}. Check nonzero_min first — SCA mode?"
    assert n_inf == 0, f"{n_inf} inf cells"
    assert n_nan == 0, f"{n_nan} nan cells"
    assert np.min(valid) == 1.0, \
        f"nonzero_min={np.min(valid):.6f} — expected 1.0. SCA mode detected."

    return {
        "max": float(max_val),
        "nonzero_min": float(np.min(valid)),
        "nonzero_count": len(valid),
        "inf": n_inf,
        "nan": n_nan,
    }


def check_d8_dinf_agreement(
    d8_accum: Path,
    dinf_accum: Path,
    tolerance: float = 0.01,
) -> dict:
    """
    Check D8/D∞ max accumulation agreement at the outlet.

    Assumption: single-outlet watershed where both algorithms integrate the
    same total contributing area. Does NOT apply to multi-outlet rasters or
    partial watershed extents.

    Returns dict with d8_max, dinf_max, ratio. Raises AssertionError if
    ratio outside [1-tolerance, 1+tolerance].
    """
    with rasterio.open(d8_accum) as src:
        d8 = src.read(1)
        d8_nodata = src.nodata
    with rasterio.open(dinf_accum) as src:
        dinf = src.read(1)
        dinf_nodata = src.nodata

    d8_valid = d8[(d8 != d8_nodata) & (d8 > 0)] if d8_nodata is not None else d8[d8 > 0]
    dinf_valid = dinf[(dinf != dinf_nodata) & (dinf > 0)] if dinf_nodata is not None else dinf[dinf > 0]

    d8_max = float(np.max(d8_valid)) if len(d8_valid) > 0 else 0.0
    dinf_max = float(np.max(dinf_valid)) if len(dinf_valid) > 0 else 0.0

    if d8_max == 0 or dinf_max == 0:
        raise AssertionError("One or both accumulations have no valid values")

    ratio = d8_max / dinf_max
    lo, hi = 1 - tolerance, 1 + tolerance

    assert lo <= ratio <= hi, \
        f"D8/D∞ ratio {ratio:.4f} outside [{lo:.2f}, {hi:.2f}]. " \
        f"D8={d8_max:,.0f}, D∞={dinf_max:,.0f}"

    return {"d8_max": d8_max, "dinf_max": dinf_max, "ratio": ratio}
