"""
Channel reachability filter: keep only stream cells whose downstream flow
path reaches a target polygon.

D8 trace follows the single steepest-descent neighbor.
D∞ trace follows both neighbors (Tarboton 1997) — boolean reachability:
a cell reaches if any non-zero flow path reaches the target.

Boolean (not flow-weighted): marks a cell as reaching even if only a
small fraction of its flow goes toward the target.  This answers the
connectivity-topology question ("does water from this cell ever arrive?")
rather than the mass-balance question ("what fraction arrives?").  For
most parcel-scale analyses, the topology question is the right one.

Memoization: global cache maps (r,c) → bool. Per-trace-origin visited set
detects cycles without poisoning the cache for other origins.

Cycle-determined results: cells in a cycle (or the immediate back-edge
origin) are stored in cycle_detected (not the main cache).  This is
conservative-safe — cycle cells are re-resolved on every encounter
rather than cached as False.  This trades a small amount of performance
for correctness on grids with pre-cycle terrain feeding into a common
cyclic basin.  The alternative (caching cycle cells when the cycle is
the whole story and no alternate path exists) is tighter but has more
edge cases.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import NamedTuple

import numpy as np
import rasterio
from rasterio import features
import geopandas as gpd


# ── D8 encoding (WBT: 1=NE,2=E,4=SE,8=S,16=SW,32=W,64=NW,128=N) ──

# dr, dc for each D8 code
_D8_DELTA: dict[int, tuple[int, int]] = {
    1: (-1, 1),     # NE
    2: (0, 1),      # E
    4: (1, 1),      # SE
    8: (1, 0),      # S
    16: (1, -1),    # SW
    32: (0, -1),    # W
    64: (-1, -1),   # NW
    128: (-1, 0),   # N
}


# ── D∞ encoding (Tarboton 1997, WBT: angle in degrees, 0=east, CCW) ──

# Neighbor (dr, dc) for each of the 8 direction indices, 0=E, 1=NE, 2=N, ...
_DINF_NEIGHBORS: list[tuple[int, int]] = [
    (0, 1),    # 0: E
    (-1, 1),   # 1: NE
    (-1, 0),   # 2: N
    (-1, -1),  # 3: NW
    (0, -1),   # 4: W
    (1, -1),   # 5: SW
    (1, 0),    # 6: S
    (1, 1),    # 7: SE
]


def _dinf_neighbors(angle_deg: float,
                    with_proportions: bool = False,
                    ) -> list[tuple]:
    """Return list of (dr, dc) [and optionally proportion] this D∞ angle flows toward.

    If with_proportions=True, returns list of (dr, dc, proportion) where
    proportions sum to 1.0.  Neighbor 1 gets (1-frac), neighbor 2 gets frac.
    Cardinal/ordinal angles (exact multiples of 45°) have only one neighbor
    with proportion 1.0.

    Boolean reachability: return both neighbors unless one gets zero flow
    (angle exactly aligned with a cardinal/ordinal direction)."""
    if angle_deg < 0 or angle_deg > 360:
        return []
    angle_deg %= 360  # normalize 360.0 and any float drift to [0, 360)

    idx1 = int(angle_deg // 45) % 8
    frac = (angle_deg - idx1 * 45) / 45.0
    idx2 = (idx1 + 1) % 8

    neighbors = []
    if frac < 1 - 1e-6:  # non-zero flow to neighbor idx1
        item = _DINF_NEIGHBORS[idx1]
        neighbors.append((*item, 1.0 - frac) if with_proportions else item)
    if frac > 1e-6:  # non-zero flow to neighbor idx2
        item = _DINF_NEIGHBORS[idx2]
        neighbors.append((*item, frac) if with_proportions else item)
    # If exactly 0 or exactly 45 etc., only one neighbor
    if not neighbors:
        item = _DINF_NEIGHBORS[idx1]
        neighbors.append((*item, 1.0) if with_proportions else item)
    return neighbors


# ── Target rasterization ──

def _rasterize_target(
    target_geom,
    ref_transform,
    ref_shape: tuple[int, int],
) -> np.ndarray:
    """Rasterize target geometry onto the reference raster grid. Returns uint8 mask."""
    mask = features.rasterize(
        [(target_geom, 1)],
        out_shape=ref_shape,
        transform=ref_transform,
        dtype="uint8",
    )
    return mask


# ── D8 reachability ──

def _d8_reachable(
    streams: np.ndarray,
    ptr: np.ndarray,
    target_mask: np.ndarray,
) -> np.ndarray:
    """Return boolean mask of stream cells whose D8 downstream path hits target_mask."""
    rows, cols = streams.shape
    cache = np.zeros((rows, cols), dtype=np.uint8)  # 0=unvisited, 1=reach, 2=no
    result = np.zeros_like(streams, dtype=bool)

    stream_cells = np.argwhere(streams > 0)

    t0 = time.time()
    n_traced = 0
    n_cache_hits = 0

    for r, c in stream_cells:
        reached, traced, cached = _d8_trace(r, c, ptr, target_mask, cache, rows, cols)
        n_traced += traced
        n_cache_hits += cached
        result[r, c] = reached

    elapsed = time.time() - t0
    n_stream = len(stream_cells)
    n_reaching = int(result.sum())
    print(f"  D8 reachable: {n_reaching:,}/{n_stream:,} stream cells "
          f"({n_reaching/n_stream*100:.1f}%), {n_traced:,} traced, "
          f"{n_cache_hits:,} cache hits, {elapsed:.1f}s")
    return result


def _d8_trace(
    r: int, c: int,
    ptr: np.ndarray,
    target_mask: np.ndarray,
    cache: np.ndarray,
    rows: int, cols: int,
) -> tuple[bool, int, int]:
    """Trace D8 downstream from (r,c). Returns (reaches, cells_traced, cache_hits)."""
    cached_val = cache[r, c]
    if cached_val:
        return cached_val == 1, 0, 1

    visited: set[tuple[int, int]] = set()
    path: list[tuple[int, int]] = [(r, c)]
    traced = 0
    result = False

    while True:
        key = (r, c)
        cached_val = cache[r, c]

        if cached_val:
            result = cached_val == 1
            break

        if target_mask[r, c]:
            result = True
            break

        if key in visited:
            result = False  # cycle
            break

        visited.add(key)
        traced += 1

        code = int(ptr[r, c])
        if code == 0 or code not in _D8_DELTA:
            result = False
            break

        dr, dc = _D8_DELTA[code]
        r, c = r + dr, c + dc

        if r < 0 or r >= rows or c < 0 or c >= cols:
            result = False
            break

        path.append((r, c))

    # Cache all cells on this path
    val = 1 if result else 2
    for pr, pc in path:
        cache[pr, pc] = val
    return result, traced, 0


# ── D∞ reachability ──

def _dinf_reachable(
    streams: np.ndarray,
    ptr: np.ndarray,
    target_mask: np.ndarray,
) -> np.ndarray:
    """Return boolean mask of stream cells whose D∞ downstream flow reaches target_mask.

    Boolean reachability: follows all non-zero-flow branches."""
    rows, cols = streams.shape
    cache = np.zeros((rows, cols), dtype=np.uint8)  # 0=unvisited, 1=reach, 2=no
    result = np.zeros_like(streams, dtype=bool)

    stream_cells = np.argwhere(streams > 0)

    t0 = time.time()
    n_traced = 0
    n_cache_hits = 0

    for r, c in stream_cells:
        reached, traced, cached = _dinf_trace(r, c, ptr, target_mask, cache, rows, cols)
        n_traced += traced
        n_cache_hits += cached
        result[r, c] = reached

    elapsed = time.time() - t0
    n_stream = len(stream_cells)
    n_reaching = int(result.sum())
    print(f"  D∞ reachable: {n_reaching:,}/{n_stream:,} stream cells "
          f"({n_reaching/n_stream*100:.1f}%), {n_traced:,} traced, "
          f"{n_cache_hits:,} cache hits, {elapsed:.1f}s")
    return result


def _dinf_trace(
    start_r: int, start_c: int,
    ptr: np.ndarray,
    target_mask: np.ndarray,
    cache: np.ndarray,
    rows: int, cols: int,
) -> tuple[bool, int, int]:
    """Iterative post-order DFS. Returns True if any non-zero D∞ branch
    from (start_r, start_c) eventually reaches a target cell.

    cache persists across calls (global memo).  Per-trace visited set
    catches cycles within a single origin trace.

    cycle_detected tracks cells whose False result was determined by
    hitting the visited set (cycle short-circuit) or by being the
    back-edge origin that flows directly into a cycle cell.  These are
    NOT written to the main cache because a different upstream cell
    might enter them via a non-cyclic path.

    Cells upstream of the cycle (whose only downstream path enters the
    cycle but are not themselves part of it) are resolved cleanly and
    cached normally."""
    cached_val = cache[start_r, start_c]
    if cached_val:
        return cached_val == 1, 0, 1

    visited: set[tuple[int, int]] = set()  # cycle detection, this trace only
    cycle_detected: set[tuple[int, int]] = set()  # cells in cycle — don't cache
    parent_of: dict[tuple[int, int], tuple[int, int]] = {}  # child → parent
    stack: list[tuple[int, int, bool]] = [(start_r, start_c, False)]
    traced = 0

    while stack:
        r, c, resolved = stack.pop()

        if resolved:
            # All children have been processed.
            if target_mask[r, c]:
                cache[r, c] = 1
                continue

            angle = float(ptr[r, c])
            neighbor_deltas = _dinf_neighbors(angle)
            valid_neighbors = []
            for dr, dc in neighbor_deltas:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    valid_neighbors.append((nr, nc))
            if not valid_neighbors:
                cache[r, c] = 2  # pit or all off-edge
                continue

            # Check children: does any reach the target?  Are all
            # non-reaching children clean (not cycle-determined)?
            # A cycle-detected child only propagates if the current
            # cell directly pushed it (parent_of[child] == self).
            # Otherwise the current cell is upstream of the cycle
            # and resolves cleanly.
            reaches = False
            all_clean = True
            for nr, nc in valid_neighbors:
                if cache[nr, nc] == 1:
                    reaches = True
                    break
                elif cache[nr, nc] == 2:
                    pass  # clean False
                elif ((nr, nc) in cycle_detected
                      and parent_of.get((nr, nc)) == (r, c)):
                    all_clean = False  # back-edge origin — propagates
                # child in cycle_detected but parent != self:
                #   upstream of cycle, treat as clean False
                # else: child not yet resolved (shouldn't happen in
                # post-order)

            if reaches:
                cache[r, c] = 1
            elif all_clean:
                cache[r, c] = 2
            else:
                cycle_detected.add((r, c))
            continue

        # First visit
        if cache[r, c] or (r, c) in cycle_detected:
            continue
        if (r, c) in visited:
            cycle_detected.add((r, c))  # cycle cell — NOT in main cache
            # The cell that pushed this one is the back-edge origin.
            parent = parent_of.get((r, c))
            if parent is not None:
                cycle_detected.add(parent)  # back-edge origin — also not cached
            continue
        visited.add((r, c))
        traced += 1

        # Target cells short-circuit; no need to explore downstream.
        if target_mask[r, c]:
            cache[r, c] = 1
            continue

        angle = float(ptr[r, c])
        neighbor_deltas = _dinf_neighbors(angle)
        valid_neighbors = []
        for dr, dc in neighbor_deltas:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                valid_neighbors.append((nr, nc))

        if not valid_neighbors:
            cache[r, c] = 2  # pit or all off-edge
            continue

        # Post-order: re-push self as resolved, then push children.
        stack.append((r, c, True))
        for nr, nc in valid_neighbors:
            if not cache[nr, nc] and (nr, nc) not in cycle_detected:
                parent_of[(nr, nc)] = (r, c)  # track back-edge origin
                stack.append((nr, nc, False))

    return cache[start_r, start_c] == 1, traced, 0


# ── Flow-weighted D∞ reachability ──


class ReachabilityResult(NamedTuple):
    streams: Path       # filtered stream raster
    fractions: Path | None  # fraction raster (None for boolean mode)


def _dinf_reachable_weighted(
    streams: np.ndarray,
    ptr: np.ndarray,
    target_mask: np.ndarray,
) -> tuple[np.ndarray, int]:
    """Return (fractions, n_cycle_truncated) for stream cells.

    fractions: float64 array, same shape as streams.  Unvisited cells = -1,
    visited cells = reachability fraction (0.0 to 1.0).
    n_cycle_truncated: number of stream cells that had cycle-truncated
    branches (fractions may be understated).

    Uses a separate visited bitmap (uint8) alongside the fraction array
    to distinguish "unvisited" (visited=0) from "resolved as 0.0" (visited=1)."""
    rows, cols = streams.shape
    visited = np.zeros((rows, cols), dtype=np.uint8)
    fractions = np.full((rows, cols), -1.0, dtype=np.float64)

    stream_cells = np.argwhere(streams > 0)
    n_cycle_truncated = 0

    t0 = time.time()
    n_traced = 0
    n_cache_hits = 0

    for r, c in stream_cells:
        frac, traced, cached, n_cycle = _dinf_weighted_trace(
            int(r), int(c), ptr, target_mask, fractions, visited, rows, cols)
        n_traced += traced
        n_cache_hits += cached
        n_cycle_truncated += n_cycle

    elapsed = time.time() - t0
    n_stream = len(stream_cells)
    fracs = np.array([fractions[ri, ci] for ri, ci in stream_cells
                       if visited[ri, ci] and fractions[ri, ci] > 0])
    n_frac_gt_001 = int(np.sum(fracs > 0.001))
    n_frac_gt_01 = int(np.sum(fracs > 0.1))
    n_frac_gt_05 = int(np.sum(fracs > 0.5))
    if n_cycle_truncated > 0:
        print(f"  D∞ flow-weighted: {n_traced:,} traced, "
              f"{n_cache_hits:,} cache hits, "
              f"{n_frac_gt_001:,} cells >0.001, "
              f"{n_frac_gt_01:,} >0.1, {n_frac_gt_05:,} >0.5, "
              f"{n_cycle_truncated} cells with cycle-truncated branches "
              f"(fractions may be understated), {elapsed:.1f}s")
    else:
        print(f"  D∞ flow-weighted: {n_traced:,} traced, "
              f"{n_cache_hits:,} cache hits, "
              f"{n_frac_gt_001:,} cells >0.001, "
              f"{n_frac_gt_01:,} >0.1, {n_frac_gt_05:,} >0.5, "
              f"{elapsed:.1f}s")
    return fractions, n_cycle_truncated


def _dinf_weighted_trace(
    start_r: int, start_c: int,
    ptr: np.ndarray,
    target_mask: np.ndarray,
    fractions: np.ndarray,
    visited: np.ndarray,
    rows: int, cols: int,
) -> tuple[float, int, int, int]:
    """Iterative post-order DFS. Returns (fraction, traced, cache_hits, n_cycle).

    fraction: reachability fraction for (start_r, start_c), 0.0 to 1.0.
    n_cycle: 1 if this cell had a cycle-truncated branch, 0 otherwise.

    visited[i,j] == 1 means fractions[i,j] holds a resolved value.
    Unvisited cells have visited[i,j] == 0 and fractions[i,j] == -1.0."""
    if visited[start_r, start_c]:
        return float(fractions[start_r, start_c]), 0, 1, 0

    # Per-trace state
    trace_visited: set[tuple[int, int]] = set()
    cycle_detected: set[tuple[int, int]] = set()
    parent_of: dict[tuple[int, int], tuple[int, int]] = {}
    stack: list[tuple[int, int, bool]] = [(start_r, start_c, False)]
    traced = 0
    n_cycle = 0

    while stack:
        r, c, resolved = stack.pop()

        if resolved:
            # All children processed.
            if target_mask[r, c]:
                fractions[r, c] = 1.0
                visited[r, c] = 1
                continue

            angle = float(ptr[r, c])
            deltas = _dinf_neighbors(angle, with_proportions=True)
            if not deltas:
                fractions[r, c] = 0.0  # pit
                visited[r, c] = 1
                continue

            cell_frac = 0.0
            for dr, dc, prop in deltas:
                nr, nc = r + dr, c + dc
                if not (0 <= nr < rows and 0 <= nc < cols):
                    continue  # off-grid → contributes 0
                if (nr, nc) in cycle_detected:
                    n_cycle = 1  # cycle branch → contributes 0
                    continue
                if visited[nr, nc]:
                    cell_frac += prop * float(fractions[nr, nc])

            fractions[r, c] = cell_frac
            visited[r, c] = 1
            continue

        # First visit
        if visited[r, c] or (r, c) in cycle_detected:
            continue
        if (r, c) in trace_visited:
            cycle_detected.add((r, c))
            parent = parent_of.get((r, c))
            if parent is not None:
                cycle_detected.add(parent)
            continue
        trace_visited.add((r, c))
        traced += 1

        # Target cells short-circuit
        if target_mask[r, c]:
            fractions[r, c] = 1.0
            visited[r, c] = 1
            continue

        angle = float(ptr[r, c])
        deltas = _dinf_neighbors(angle, with_proportions=True)
        if not deltas:
            fractions[r, c] = 0.0  # pit
            visited[r, c] = 1
            continue

        stack.append((r, c, True))
        for dr, dc, prop in deltas:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            if not visited[nr, nc] and (nr, nc) not in cycle_detected:
                parent_of[(nr, nc)] = (r, c)
                stack.append((nr, nc, False))

    return float(fractions[start_r, start_c]), traced, 0, n_cycle


# ── Public API ──

def filter_reachable(
    streams: Path,
    pointer: Path,
    target_geom_path: Path,
    output: Path | None = None,
    *,
    pointer_type: str = "d8",
    buffer_m: float = 3.0,
    reachability_mode: str = "boolean",
) -> ReachabilityResult:
    """Filter stream raster to cells whose flow reaches the target geometry.

    Parameters
    ----------
    streams : Path
        Binary stream raster (uint8, 0/1).
    pointer : Path
        Flow direction pointer raster. D8: int16 (WBT encoding). D∞: float32 (degrees).
    target_geom_path : Path
        GeoJSON path to target polygon (e.g., parcel boundary).
    output : Path or None
        Output path for filtered stream raster. Default: streams with '_reachable' suffix.
    pointer_type : str
        'd8' or 'dinf'.
    buffer_m : float
        Buffer distance in meters around target geometry (registration tolerance).
    reachability_mode : str
        'boolean' (default) or 'flow_weighted'.  Flow-weighted computes the
        fraction of each cell's flow that reaches the target (D∞ only; D8
        falls back to boolean since single-path fractions are always 0 or 1).

    Returns
    -------
    ReachabilityResult with .streams (Path) and .fractions (Path | None)."""
    streams = Path(streams).resolve()
    pointer = Path(pointer).resolve()
    target_geom_path = Path(target_geom_path).resolve()

    if output is None:
        output = streams.parent / f"{streams.stem}_reachable.tif"
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    # Load raster metadata
    with rasterio.open(streams) as src_s:
        sdata = src_s.read(1)
        s_profile = src_s.profile.copy()
        s_crs = src_s.crs
        s_transform = src_s.transform
        s_shape = src_s.shape

    with rasterio.open(pointer) as src_p:
        pdata = src_p.read(1)
        p_crs = src_p.crs
        p_transform = src_p.transform
        p_shape = src_p.shape

    # Alignment assertions
    assert s_crs == p_crs, f"CRS mismatch: streams={s_crs}, pointer={p_crs}"
    assert s_transform == p_transform, "Transform mismatch"
    assert s_shape == p_shape, f"Shape mismatch: streams={s_shape}, pointer={p_shape}"

    # Load and reproject target
    target_gdf = gpd.read_file(target_geom_path)
    if target_gdf.crs is None:
        raise ValueError(f"Target geometry has no CRS: {target_geom_path}")
    target_gdf = target_gdf.to_crs(s_crs)

    # Buffer target in CRS units (EPSG:5070 = meters)
    target_geom = target_gdf.geometry.iloc[0]
    if buffer_m > 0:
        target_geom = target_geom.buffer(buffer_m)

    # Rasterize target
    target_mask = _rasterize_target(target_geom, s_transform, s_shape)
    n_target = int(target_mask.sum())
    if n_target == 0:
        raise ValueError(
            f"Target geometry rasterized to 0 cells. "
            f"Check CRS alignment: target in {target_gdf.crs}, rasters in {s_crs}"
        )
    print(f"  Target: {n_target:,} cells (buffer={buffer_m}m)")

    # Filter
    fraction_raster = None
    if reachability_mode == "flow_weighted" and pointer_type == "dinf":
        fractions, n_cycle = _dinf_reachable_weighted(sdata, pdata, target_mask)
        # Derive boolean reachable from fractions
        reachable = np.zeros_like(sdata, dtype=bool)
        for r, c in np.argwhere(sdata > 0):
            reachable[r, c] = (fractions[r, c] > 0.0)
        # Write fraction raster
        frac_path = output.parent / f"{output.stem}_fractions.tif"
        frac_data = np.where(reachable, fractions, 0.0).astype("float32")
        frac_profile = s_profile.copy()
        frac_profile.update(dtype="float32", compress="lzw", nodata=0.0)
        with rasterio.open(frac_path, "w", **frac_profile) as dst:
            dst.write(frac_data, 1)
        fraction_raster = frac_path
    elif pointer_type == "d8":
        reachable = _d8_reachable(sdata, pdata, target_mask)
    elif pointer_type == "dinf":
        reachable = _dinf_reachable(sdata, pdata, target_mask)
    else:
        raise ValueError(f"Unknown pointer_type: {pointer_type}")

    # Write filtered streams
    filtered = np.where(reachable, sdata, 0).astype("uint8")
    s_profile.update(compress="lzw")
    with rasterio.open(output, "w", **s_profile) as dst:
        dst.write(filtered, 1)

    n_before = int((sdata > 0).sum())
    n_after = int((filtered > 0).sum())
    print(f"  Filtered: {n_before:,} → {n_after:,} cells "
          f"({n_after/n_before*100:.1f}% kept) → {output}")
    return ReachabilityResult(streams=output, fractions=fraction_raster)
