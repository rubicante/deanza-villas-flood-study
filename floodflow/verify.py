"""Verification functions for flow accumulation rasters.

Key spike lessons:
  - nonzero_min == 1 catches SCA default on D∞ (nonzero_min would be cell width)
  - isfinite(max) BEFORE trusting max (inf renders max meaningless)
"""

from pathlib import Path

import numpy as np
import rasterio

from floodflow.encoding import D8_DELTA, dinf_neighbors


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


def verify_monotonicity_along_paths(
    accum: Path,
    pointer: Path,
    pointer_type: str = "d8",
    n_samples: int = 1000,
    max_steps: int = 20,
) -> dict:
    """Sample stream cells and walk downstream, asserting accumulation is
    non-decreasing along each path.

    For D8: follows the single steepest-descent neighbor. Strictly
    non-decreasing (upstream accum ≤ downstream accum).

    For D∞: follows the primary Tarboton neighbor (larger flow fraction).
    Accumulation is not monotonic under flow splitting, but each receiving
    neighbor must hold at least the share this cell sends it:
    accum[nbr] >= proportion * accum[cell] (relative tolerance 1e-4 for
    float32). Paths whose pointer leads off-grid are counted separately and
    tolerated up to 1% (normal at the edge of a small DEM).

    Catches: encoding-table corruption, masking off-by-ones, nodata
    leakage — bugs that corrupt the flow field without changing the
    outlet maximum.

    Returns dict with n_samples, max_steps, violations.
    Raises AssertionError if any violation found."""
    import random

    with rasterio.open(accum) as src:
        a = src.read(1)
        a_nodata = src.nodata
    with rasterio.open(pointer) as src:
        p = src.read(1)

    rows, cols = a.shape

    # Valid cells: positive accum, valid pointer
    if a_nodata is not None:
        valid = (a != a_nodata) & (a > 0)
    else:
        valid = a > 0

    if pointer_type == "d8":
        valid = valid & (p > 0) & (p <= 128)
        valid_rows, valid_cols = np.where(valid)
        if len(valid_rows) == 0:
            return {"n_samples": 0, "max_steps": max_steps, "violations": 0}

        n = min(n_samples, len(valid_rows))
        rng = random.Random(42)
        idxs = rng.sample(range(len(valid_rows)), n)
        violations = 0

        for idx in idxs:
            r, c = int(valid_rows[idx]), int(valid_cols[idx])
            for step in range(max_steps):
                code = int(p[r, c])
                if code == 0 or code not in D8_DELTA:
                    break
                dr, dc = D8_DELTA[code]
                nr, nc = r + dr, c + dc
                if not (0 <= nr < rows and 0 <= nc < cols):
                    break
                if a[nr, nc] <= 0:  # reached edge or nodata
                    break
                if a[r, c] > a[nr, nc]:
                    violations += 1
                    break  # one violation per path
                r, c = nr, nc

        assert violations == 0, (
            f"D8 monotonicity: {violations}/{n} paths violated "
            f"(accum decreased along flow path)")

        print(f"  D8 monotonicity: {n} paths × {max_steps} steps, "
              f"{violations} violations")
        return {"n_samples": n, "max_steps": max_steps,
                "violations": violations}

    elif pointer_type == "dinf":
        valid = valid & (p >= 0) & (p <= 360)
        valid_rows, valid_cols = np.where(valid)
        if len(valid_rows) == 0:
            return {"n_samples": 0, "max_steps": max_steps, "violations": 0}

        n = min(n_samples, len(valid_rows))
        rng = random.Random(42)
        idxs = rng.sample(range(len(valid_rows)), n)
        violations = 0
        edge_paths = 0

        for idx in idxs:
            r, c = int(valid_rows[idx]), int(valid_cols[idx])
            for step in range(max_steps):
                angle = float(p[r, c])
                if angle == -1.0:  # WBT flat/peak terminus — legitimate endpoint
                    break
                nbrs = dinf_neighbors(angle, with_proportions=True)
                if not nbrs:
                    edge_paths += 1
                    break
                on_grid = [(r + dr, c + dc, f) for dr, dc, f in nbrs
                           if 0 <= r + dr < rows and 0 <= c + dc < cols]
                if not on_grid:
                    edge_paths += 1
                    break
                bad = False
                for nr, nc, f in on_grid:
                    if a[nr, nc] <= 0:  # masked out / nodata downstream
                        continue
                    share = f * float(a[r, c])
                    if float(a[nr, nc]) < share * (1 - 1e-4):
                        bad = True
                if bad:
                    violations += 1
                    break  # one violation per path
                nr, nc, _ = max(on_grid, key=lambda t: t[2])
                if a[nr, nc] <= 0:
                    break
                r, c = nr, nc

        assert violations == 0, (
            f"D∞ accumulation: {violations}/{n} paths violated "
            f"(downstream neighbor holds less than its received share)")
        if edge_paths > n * 0.01:
            raise AssertionError(
                f"D∞ pointer validity: {edge_paths}/{n} paths had no on-grid "
                f"downstream neighbor (pit or grid edge)")
        print(f"  D∞ accumulation: {n} paths × {max_steps} steps, "
              f"{violations} violations, {edge_paths} edge paths")
        return {"n_samples": n, "max_steps": max_steps,
                "violations": violations, "edge_paths": edge_paths}

    else:
        raise ValueError(f"Unknown pointer_type: {pointer_type}")
