# Parcel-Centered Pipeline Consolidation Plan

> **Audience:** A competent developer with zero prior context. No knowledge of
> the codebase, terrain, or tooling is assumed.

**Goal:** Replace the dual-geometry pipeline (community bbox pour point + parcel
reachability target) with a single parcel-centered contributing area.

**Architecture:** New `deliverable/upstream.py` module for D∞ upstream trace.
`_henderson.py` build functions switch boundary. Reachability filter removed
(redundant when watershed IS the contributing area). Web explorer updated.

**Tech stack:** Python 3.13, numpy, rasterio, geopandas, shapely, whitebox,
pyflwdir. All in project venv.

---

## Recovery Analysis

### What this project is

Geospatial flood-risk study for the De Anza Villas mobile home park in Borrego
Springs, California. Core question: which upstream terrain drains to this
parcel, and what does that flow network look like? Output is an interactive web
map (the "stream explorer") showing stream cells colored by upstream
accumulation, toggleable between D8 and D∞ flow models at 1m and 10m resolution.

### Current pipeline (what's wrong)

Two geometries govern the pipeline, creating confusion:

```
community_bbox → D∞ upstream trace → 33.6 km² Henderson boundary
                                                      ↓
                                          +200m buffer → clip DEM
                                                      ↓
                                          D8/D∞ pointer + accumulation
                                                      ↓
                                          extract streams (t=250)
                                                      ↓
                                          downstream trace to PARCEL
                                          (reachability filter)
                                                      ↓
                                          binary export (reachable only)
```

The community bbox (`deanza_community_bbox.geojson`) is used ONCE as the pour
point for watershed delineation. The parcel (`deanza_villas_complex_boundary.geojson`)
is used downstream as the reachability target. The community bbox has no other
purpose. Everything the web explorer shows is filtered to parcel-reachable cells.

### Consolidation goal

The parcel becomes the single area of interest:

```
parcel + 3m buffer → D∞ upstream trace → parcel contributing area polygon
                                                      ↓
                                          +200m buffer → clip DEM
                                                      ↓
                                          D8/D∞ pointer + accumulation
                                                      ↓
                                          extract streams (t=250)
                                          (all streams reach parcel by definition)
                                                      ↓
                                          binary export (all streams)
```

Why D∞ for the upstream trace: D8 upstream trace from the community bbox gave
4.2 km² — too conservative, flow chains break on the flat fan surface. D∞
upstream trace gave the accepted 33.6 km². Same logic applies to the parcel.

Why skip reachability: if the watershed IS the contributing area, by
construction every stream cell within it drains to the parcel. The reachability
filter becomes a no-op. Verify with spot-check.

### What changes in the web explorer

- Watershed boundary: Henderson 33.6 km² → parcel contributing area polygon
- Remove community bbox layer (pour-point zone toggle)
- Remove "⇢ De Anza Villas only" indicator — all cells are reachable
- Revert "Reachable cells" → "Stream cells" stat label
- Binary files are larger (all streams, not just reachable subset)
- Map viewport centers on smaller extent

### Memory assessment

The parcel contributing area is a subset of 33.6 km² (parcel ⊂ community).
Likely 5–25 km² = 5–25M cells at 1m, fitting comfortably in 7.6 GB without
multi-process memory isolation.

### What survives unchanged

- `deliverable/d8.py`, `dinf.py`, `reachability.py`, `streams.py`, `verify.py`,
  `preprocess.py`, `fetch.py`
- Binary format (uint32 header + stride-3 float32 [accum, lon, lat])
- Web explorer rendering engine (canvas overlay, binary search, color scales)
- WBT as engine, pyflwdir for D8 accum with watershed masking

### What gets retired

- `deanza_community_bbox.geojson` — no longer referenced
- `henderson_watershed_boundary.geojson` and `*_5070.geojson` — replaced
- `build_watershed_boundary()` function — replaced by upstream trace
- `deliverable/watershed.py` — replaced by `deliverable/upstream.py`
- All existing 1m and 10m rasters (regenerated on new extent)
- Reachability filter calls in build functions (redundant)

---

## Implementation Plan

### Task 1: Create `deliverable/upstream.py`

**Objective:** D∞ upstream trace from a target geometry to contributing-area
mask + polygonized boundary.

**New file:** `deliverable/upstream.py`

**Step 1: Write the module**

```python
"""D∞ upstream trace: find all cells whose flow reaches a target polygon.

Boolean contributing area: a cell is included if ANY non-zero D∞ flow
branch eventually reaches the target. This matches the semantics used for
the accepted Henderson watershed boundary (33.6 km² from community bbox).
"""

import numpy as np
import rasterio
from rasterio import features
from shapely.geometry import shape
from shapely.ops import unary_union
import geopandas as gpd
from pathlib import Path
from collections import deque
import time


# D∞ neighbor lookup: direction index → (dr, dc)
# Index 0=E, 1=NE, 2=N, 3=NW, 4=W, 5=SW, 6=S, 7=SE
_DINF_NEIGHBORS = [
    (0, 1), (-1, 1), (-1, 0), (-1, -1),
    (0, -1), (1, -1), (1, 0), (1, 1),
]


def _neighbors_flowing_into(r: int, c: int, ptr: np.ndarray,
                             rows: int, cols: int) -> list[tuple[int, int]]:
    """Return list of (nr, nc) cells whose D∞ flow points toward (r, c).

    For each of the 8 neighbors, check whether the neighbor's D∞ angle
    (WBT encoding: degrees, 0=east, CCW) includes the reverse direction.
    A neighbor at direction index `out_idx` from the target means the
    target is at direction `(out_idx + 4) % 8` from the neighbor.
    """
    result = []
    for out_idx, (dr, dc) in enumerate(_DINF_NEIGHBORS):
        nr, nc = r + dr, c + dc
        if nr < 0 or nr >= rows or nc < 0 or nc >= cols:
            continue
        angle = float(ptr[nr, nc])
        if angle < 0 or angle >= 360:  # nodata or edge value (360° = 0°)
            continue
        angle %= 360  # normalize 360.0 → 0.0, any float drift
        # Reverse direction: (out_idx + 4) % 8
        rev_dir = (out_idx + 4) % 8
        idx1 = int(angle // 45) % 8
        frac = (angle - idx1 * 45) / 45.0
        flows_to_rev = ((idx1 == rev_dir and frac < 1 - 1e-6) or
                        ((idx1 + 1) % 8 == rev_dir and frac > 1e-6))
        if flows_to_rev:
            result.append((nr, nc))
    return result


def contributing_area(
    pointer: Path,
    target_gdf: gpd.GeoDataFrame,
    output_mask: Path | None = None,
    output_boundary: Path | None = None,
    *,
    simplify_m: float = 10.0,
    edge_check: bool = True,
) -> gpd.GeoDataFrame:
    """Compute D∞ upstream contributing area to a target geometry.

    Parameters
    ----------
    pointer : Path
        D∞ flow direction raster (float32, angle in degrees, WBT encoding).
        Must cover the full upstream contributing area.
    target_gdf : gpd.GeoDataFrame
        Target polygon. Reprojected to pointer CRS internally.
    output_mask : Path or None
        Optional path for contributing area mask GeoTIFF (uint8).
    output_boundary : Path or None
        Optional path for polygonized boundary GeoJSON (EPSG:5070).
    simplify_m : float
        Simplification tolerance in meters (default 10m).
    edge_check : bool
        If True, warn when contributing area reaches pointer edge.

    Returns
    -------
    gpd.GeoDataFrame
        WGS84 boundary polygon with properties: name, area_km2, cells,
        resolution_m, trace_type='boolean_dinf'.
    """
    pointer = Path(pointer).resolve()

    with rasterio.open(pointer) as src:
        ptr = src.read(1)
        p_crs = src.crs
        p_transform = src.transform
        p_shape = src.shape
        p_res = abs(p_transform.a)

    rows, cols = p_shape

    # Rasterize target
    tgdf = target_gdf.to_crs(p_crs)
    target_mask = features.rasterize(
        [(tgdf.geometry.iloc[0], 1)],
        out_shape=p_shape,
        transform=p_transform,
        dtype="uint8",
    )
    n_target = int(target_mask.sum())
    if n_target == 0:
        raise ValueError("Target geometry rasterized to 0 cells")
    print(f"  Target: {n_target:,} cells")

    # BFS upstream trace
    visited = np.zeros(p_shape, dtype="uint8")
    queue = deque()

    seed_rows, seed_cols = np.where(target_mask > 0)
    for r, c in zip(seed_rows, seed_cols):
        visited[r, c] = 1
        queue.append((int(r), int(c)))

    print(f"  Tracing upstream from {len(queue):,} seed cells…")
    t0 = time.time()
    while queue:
        r, c = queue.popleft()
        for nr, nc in _neighbors_flowing_into(r, c, ptr, rows, cols):
            if not visited[nr, nc]:
                visited[nr, nc] = 1
                queue.append((nr, nc))

    n_contrib = int(visited.sum())
    area_km2 = n_contrib * p_res * p_res / 1e6
    print(f"  Contributing area: {n_contrib:,} cells, {area_km2:.1f} km² "
          f"in {time.time() - t0:.0f}s")

    # Edge-touch check
    if edge_check:
        cr, cc = np.where(visited > 0)
        if (cr.min() < 2 or cr.max() > rows - 3 or
            cc.min() < 2 or cc.max() > cols - 3):
            print("  WARNING: Contributing area touches pointer edge. "
                  "The pointer extent may be too small to capture the "
                  "full upstream area.")

    # Save mask
    if output_mask:
        output_mask = Path(output_mask)
        output_mask.parent.mkdir(parents=True, exist_ok=True)
        prof = {"driver": "GTiff", "count": 1, "height": rows,
                "width": cols, "transform": p_transform, "crs": p_crs,
                "dtype": "uint8", "compress": "lzw"}
        with rasterio.open(output_mask, "w", **prof) as dst:
            dst.write(visited, 1)
        print(f"  Mask → {output_mask}")

    # Polygonize
    binary = visited.astype("int16")
    results = list(features.shapes(binary, mask=visited,
                                   transform=p_transform))
    geoms = [shape(g) for g, v in results if v == 1]
    if not geoms:
        raise RuntimeError("Polygonization produced zero geometries")
    merged = unary_union(geoms)
    simplified = merged.simplify(simplify_m, preserve_topology=True)
    print(f"  Polygonized: {len(geoms)} fragments → {simplified.geom_type}")

    gdf_5070 = gpd.GeoDataFrame(
        [{"name": "Parcel contributing area",
          "area_km2": round(area_km2, 2),
          "cells": int(n_contrib),
          "resolution_m": p_res,
          "trace_type": "boolean_dinf"}],
        geometry=[simplified],
        crs=p_crs,
    )

    if output_boundary:
        output_boundary = Path(output_boundary)
        output_boundary.parent.mkdir(parents=True, exist_ok=True)
        gdf_5070.to_file(output_boundary, driver="GeoJSON")
        print(f"  Boundary → {output_boundary}")

    return gdf_5070.to_crs("EPSG:4326")
```

**Step 2: Verify syntax**

```bash
cd /home/hermes/workspace/deanza-villas-flood-study
.venv/bin/python -m pyflakes deliverable/upstream.py
```

Expected: clean, no output.

**Step 3: Commit**

```bash
git add deliverable/upstream.py
git commit -m "feat: add D∞ upstream contributing area trace"
```

---

### Task 2: Compute the parcel contributing area boundary

**Objective:** Run the upstream trace using the existing 1m D∞ pointer.

> **Bootstrap note:** This trace runs on the CURRENT `dinf_pointer_1m.tif`
> (built on the old community-bbox clip). Task 5 will delete this pointer
> and rebuild on a new DEM clipped to the contributing area + 200m buffer.
> The boundary produced here defines the new clip extent — a one-time
> bootstrap. Do not re-trace after Task 5; the boundary is a frozen
> artifact from this step.

**Step 1: Write runner script**

Create `spikes/compute_contributing_area.py`:

```python
"""One-shot: compute De Anza Villas parcel contributing area from existing
1m D∞ pointer."""
import sys
from pathlib import Path
import geopandas as gpd

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
sys.path.insert(0, str(ROOT))

from deliverable.upstream import contributing_area

PTR = ROOT / "data/derived/henderson/dinf_pointer_1m.tif"
PARCEL = ROOT / "data/raw/sangis/deanza_villas_complex_boundary.geojson"
OUT_MASK = ROOT / "data/derived/henderson/parcel_contributing_area.tif"
OUT_5070 = ROOT / "data/derived/vectors/deanza_parcel_contributing_area_5070.geojson"

parcel = gpd.read_file(PARCEL)
parcel_buffered = parcel.copy()
parcel_buffered.geometry = parcel.geometry.buffer(3.0)

# Confirm pointer NoData encoding (should be -32768 or negative)
import rasterio
with rasterio.open(PTR) as src:
    nd = src.nodata
    print(f"  D∞ pointer nodata: {nd}")

gdf_4326 = contributing_area(
    PTR, parcel_buffered,
    output_mask=OUT_MASK,
    output_boundary=OUT_5070,
)

OUT_WGS84 = ROOT / "data/derived/vectors/deanza_parcel_contributing_area.geojson"
OUT_WGS84.parent.mkdir(parents=True, exist_ok=True)
gdf_4326.to_file(OUT_WGS84, driver="GeoJSON")
print(f"WGS84 → {OUT_WGS84}")
print(f"\nProperties:\n{gdf_4326[['name','area_km2','cells','trace_type']]}")
```

**Step 2: Run**

```bash
cd /home/hermes/workspace/deanza-villas-flood-study
.venv/bin/python spikes/compute_contributing_area.py
```

Expected: area < 33.6 km², no edge-touch warning, single contiguous polygon.

**Step 3: Inspect**

```bash
.venv/bin/python -c "
import geopandas as gpd
gdf = gpd.read_file('data/derived/vectors/deanza_parcel_contributing_area.geojson')
print(gdf[['name','area_km2','cells']].to_string())
print('Bounds:', gdf.total_bounds)
"
```

Verify area is plausible (likely 5–25 km²).

**Step 4: Commit**

```bash
git add spikes/compute_contributing_area.py
git add data/derived/vectors/deanza_parcel_contributing_area*.geojson
git add data/derived/henderson/parcel_contributing_area.tif
git commit -m "feat: parcel contributing area boundary from D∞ upstream trace"
```

---

### Task 3: Update `_henderson.py` build functions

**Objective:** Switch from Henderson watershed to parcel contributing area.
Remove reachability filter. Remove watershed delineation function.

**Modify:** `deliverable/_henderson.py`

**Step 1: Replace boundary constant**

Change line 30 from:
```python
BOUNDARY = DATA / "henderson_watershed_boundary.geojson"
```
to:
```python
CONTRIBUTING_AREA = DATA / "deanza_parcel_contributing_area.geojson"
CONTRIBUTING_AREA_5070 = DATA / "deanza_parcel_contributing_area_5070.geojson"
```

**Step 2: Remove old imports**

Delete:
- `from deliverable.watershed import delineate_watershed` (line 21)
- `from deliverable.reachability import filter_reachable` (line 22)

**Step 3: Update `build_dinf_1m()`**

Replace all `BOUNDARY` references with `CONTRIBUTING_AREA` or
`CONTRIBUTING_AREA_5070`. Remove the `filter_reachable()` call (line 127).
Change the binary boundary reference. After changes:

```python
def build_dinf_1m():
    """D∞ 1m for parcel contributing area."""
    DERIVED.mkdir(parents=True, exist_ok=True)
    dem = DERIVED / "dem_1m_filled_f32.tif"
    accum = DERIVED / "dinf_flow_accum_1m.tif"
    accum_masked = DERIVED / "dinf_flow_accum_1m_masked.tif"
    dinf_ptr = DERIVED / "dinf_pointer_1m.tif"
    streams = DERIVED / "streams_dinf_1m_250.tif"

    if not dem.exists():
        raw = fetch_dem(CONTRIBUTING_AREA, resolution=1.0, crs=TARGET_CRS,
                        buffer_m=200, output=DERIVED / "dem_1m_clipped.tif")
        dem = preprocess_dem(raw, output=dem)

    compute_dinf(dem, output=accum, pointer=dinf_ptr)

    # Mask to contributing area
    ws = gpd.read_file(CONTRIBUTING_AREA)
    ws_5070 = ws.to_crs(TARGET_CRS)
    with rasterio.open(accum) as src:
        da = src.read(1)
        prof = src.profile.copy()
    ws_mask = rasterio.features.rasterize(
        [(ws_5070.geometry.iloc[0], 1)],
        out_shape=da.shape, transform=prof["transform"], dtype="uint8")
    masked = np.where(ws_mask, da, 0).astype(prof["dtype"])
    with rasterio.open(accum_masked, "w", **prof) as dst:
        dst.write(masked, 1)

    verify_accumulation(accum_masked)
    extract_streams(accum_masked, threshold=250, output=streams)
    _export_binary(streams, accum_masked, MAPS / "streams_all.bin",
                   boundary=CONTRIBUTING_AREA)
```

**Step 4: Update `build_dinf_10m()`**

Same pattern as 10m — replace BOUNDARY with CONTRIBUTING_AREA, remove
filter_reachable, replace `watershed_wide.tif` with rasterization (matching
1m pattern), update binary boundary.

```python
def build_dinf_10m():
    """D∞ 10m for parcel contributing area."""
    DERIVED.mkdir(parents=True, exist_ok=True)
    dem = DERIVED / "dem_10m_filled.tif"
    accum = DERIVED / "dinf_flow_accum_10m.tif"
    dinf_ptr = DERIVED / "dinf_pointer_10m.tif"
    accum_masked = DERIVED / "dinf_flow_accum_10m_masked.tif"
    streams = DERIVED / "streams_dinf_10m_250.tif"

    if not dem.exists():
        dem = preprocess_dem(DEM_10M, output=dem, strategy="breach_then_fill")

    compute_dinf(dem, output=accum, pointer=dinf_ptr)

    # Rasterize contributing area (matches 1m pattern; no watershed_wide.tif)
    ws = gpd.read_file(CONTRIBUTING_AREA)
    ws_5070 = ws.to_crs(TARGET_CRS)
    with rasterio.open(accum) as src:
        da = src.read(1)
        prof = src.profile.copy()
    ws_mask = rasterio.features.rasterize(
        [(ws_5070.geometry.iloc[0], 1)],
        out_shape=da.shape, transform=prof["transform"], dtype="uint8")
    masked = np.where(ws_mask, da, 0).astype(prof["dtype"])
    with rasterio.open(accum_masked, "w", **prof) as dst:
        dst.write(masked, 1)

    verify_accumulation(accum_masked)
    extract_streams(accum_masked, threshold=250, output=streams)
    _export_binary(streams, accum_masked, MAPS / "streams_wide_dinf.bin",
                   boundary=CONTRIBUTING_AREA)
```

**Step 5: Update `build_d8_1m()`**

Replace BOUNDARY, remove filter_reachable. The `watershed_geom` parameter
already works — just point it to the new file.

```python
def build_d8_1m():
    """D8 1m for parcel contributing area."""
    DERIVED.mkdir(parents=True, exist_ok=True)
    dem = DERIVED / "dem_1m_filled_f32.tif"
    ptr = DERIVED / "d8_pointer_1m.tif"
    accum = DERIVED / "d8_flow_accum_1m.tif"
    accum_masked = DERIVED / "d8_flow_accum_1m_masked.tif"
    streams = DERIVED / "streams_d8_1m_250.tif"

    if not dem.exists():
        raw = fetch_dem(CONTRIBUTING_AREA, resolution=1.0, crs=TARGET_CRS,
                        buffer_m=200, output=DERIVED / "dem_1m_clipped.tif")
        dem = preprocess_dem(raw, output=dem)

    compute_d8_pointer(dem, output=ptr)
    compute_d8_accum(dem, output=accum, pointer=ptr,
                     backend="wbt_ptr_pyflwdir",
                     watershed_geom=CONTRIBUTING_AREA_5070)

    # Belt-and-suspenders accum mask
    ws = gpd.read_file(CONTRIBUTING_AREA)
    ws_5070 = ws.to_crs(TARGET_CRS)
    with rasterio.open(accum) as src:
        da = src.read(1)
        prof = src.profile.copy()
    ws_mask = rasterio.features.rasterize(
        [(ws_5070.geometry.iloc[0], 1)],
        out_shape=da.shape, transform=prof["transform"], dtype="uint8")
    masked = np.where(ws_mask, da, 0).astype(prof["dtype"])
    with rasterio.open(accum_masked, "w", **prof) as dst:
        dst.write(masked, 1)

    verify_accumulation(accum_masked)
    dinf = DERIVED / "dinf_flow_accum_1m.tif"
    if dinf.exists():
        check_d8_dinf_agreement(accum, dinf, tolerance=0.07)
    extract_streams(accum_masked, threshold=250, output=streams)
    _export_binary(streams, accum_masked, MAPS / "streams_d8_1m.bin",
                   boundary=CONTRIBUTING_AREA)
```

**Step 6: Update `build_d8_10m()`**

Same pattern as D∞ 10m — remove `watershed_wide.tif` dependency, use
rasterization.

```python
def build_d8_10m():
    """D8 10m for parcel contributing area."""
    DERIVED.mkdir(parents=True, exist_ok=True)
    dem = DERIVED / "dem_10m_filled.tif"
    ptr = DERIVED / "d8_pointer_10m.tif"
    accum = DERIVED / "d8_flow_accum_10m.tif"
    accum_masked = DERIVED / "d8_flow_accum_10m_masked.tif"
    streams = DERIVED / "streams_d8_10m_250.tif"

    if not dem.exists():
        dem = preprocess_dem(DEM_10M, output=dem, strategy="breach_then_fill")

    compute_d8_pointer(dem, output=ptr)
    compute_d8_accum(dem, output=accum, pointer=ptr,
                     backend="wbt_ptr_pyflwdir")

    # Rasterize contributing area
    ws = gpd.read_file(CONTRIBUTING_AREA)
    ws_5070 = ws.to_crs(TARGET_CRS)
    with rasterio.open(accum) as src:
        da = src.read(1)
        prof = src.profile.copy()
    ws_mask = rasterio.features.rasterize(
        [(ws_5070.geometry.iloc[0], 1)],
        out_shape=da.shape, transform=prof["transform"], dtype="uint8")
    masked = np.where(ws_mask, da, 0).astype(prof["dtype"])
    with rasterio.open(accum_masked, "w", **prof) as dst:
        dst.write(masked, 1)

    verify_accumulation(accum_masked)
    extract_streams(accum_masked, threshold=250, output=streams)
    _export_binary(streams, accum_masked, MAPS / "streams_wide_d8.bin",
                   boundary=CONTRIBUTING_AREA)
```

**Step 7: Delete `build_watershed_boundary()`**

Remove the entire function (old lines 242–256).

**Step 8: Update `__main__` block**

Remove `"watershed"` from usage string and command dispatch. Remove
`build_watershed_boundary()` from the `"all"` chain.

```python
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python _henderson.py [dinf1m|dinf10m|d81m|d810m|all]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "dinf1m":
        build_dinf_1m()
    elif cmd == "dinf10m":
        build_dinf_10m()
    elif cmd == "d81m":
        build_d8_1m()
    elif cmd == "d810m":
        build_d8_10m()
    elif cmd == "all":
        build_dinf_1m()
        build_dinf_10m()
        build_d8_1m()
        build_d8_10m()
    else:
        print(f"Unknown: {cmd}")
        sys.exit(1)
```

**Step 9: Verify no stale references**

```bash
grep -n "BOUNDARY\|watershed_wide\|filter_reachable\|community_bbox\|delineate_watershed" \
  deliverable/_henderson.py
```

Expected: no matches.

**Step 10: Lint and commit**

```bash
.venv/bin/python -m pyflakes deliverable/_henderson.py
git add deliverable/_henderson.py
git commit -m "refactor: parcel contributing area boundary, remove reachability filter"
```

**Optional: Factor the repeated rasterize-and-mask block**

All four build functions now contain ~12 identical lines that rasterize the
contributing area polygon onto an accumulation grid and mask it. Worth
extracting into a helper:

```python
def _mask_to_boundary(raster_path: Path, boundary_path: Path,
                      output_path: Path) -> Path:
    """Mask a raster to a GeoJSON boundary polygon. Returns output Path."""
    gdf = gpd.read_file(boundary_path)
    gdf = gdf.to_crs(TARGET_CRS)
    with rasterio.open(raster_path) as src:
        data = src.read(1)
        prof = src.profile.copy()
    mask = rasterio.features.rasterize(
        [(gdf.geometry.iloc[0], 1)],
        out_shape=data.shape, transform=prof["transform"], dtype="uint8")
    masked = np.where(mask, data, 0).astype(prof["dtype"])
    with rasterio.open(output_path, "w", **prof) as dst:
        dst.write(masked, 1)
    return output_path
```

Replace the 12-line block in each build function with a one-liner:
`accum_masked = _mask_to_boundary(accum, CONTRIBUTING_AREA, accum_masked)`.

This also means you could remove the `watershed_geom` belt from `compute_d8_accum`
and let the mask helper handle it uniformly — one path to maintain, not two.

---

### Task 4: Update web explorer

**Objective:** New boundary, remove community bbox, remove reachability
indicator.

**Modify:** `outputs/maps/stream_explorer.html`

> **Note on line numbers:** The file was edited (May 9, 2026) to add
> reachability labels. Line numbers below reference the CURRENT state of
> the file. Use content matching if line numbers drift.

**Step 1: Update boundary URL (line 117)**

```javascript
const WATERSHED_URL = 'deanza_parcel_contributing_area.geojson';
```

**Step 2: Remove pour-point constants and variables**

Remove `POURPOINT_URL` constant declaration (currently ~line 120):
```javascript
const POURPOINT_URL = 'deanza_community_bbox.geojson';
```

Remove `pourpointData` from the variable declaration (line 297):
```javascript
// Before: let huc12Data=null, pourpointData=null, femaData=null, ...
// After:  let huc12Data=null, femaData=null, ...
```

Remove the fetch call for pourpoint (line 299):
```javascript
try { pourpointData = await fetch(POURPOINT_URL).then(r => r.json()); } catch(e) { console.warn('Pourpoint:', e); }
```

**Step 3: Remove pour-point source, layer, and toggle**

Delete the source/layer block (lines 356–358):
```javascript
if (pourpointData) {
  map.addSource('pourpoint', { type: 'geojson', data: pourpointData });
  map.addLayer({ id: 'pourpoint-line', type: 'line', source: 'pourpoint',
    paint: { 'line-color': '#8b949e', 'line-width': 1.5,
             'line-dasharray': [4,4], 'line-opacity': 0.7 },
    layout: { visibility: 'none' } }, 'aoi-2km-line');
}
```

Delete the legend item (lines 67–71 in the legend div):
```html
<label class="legend-item" for="tog-pourpoint">
  <input type="checkbox" id="tog-pourpoint">
  <span class="legend-line" style="border-top:1.5px dashed #8b949e"></span>
  <span class="label-text">Watershed pour-point zone</span>
</label>
```

Delete the toggle binding:
```javascript
bindLayerToggle('tog-pourpoint', ['pourpoint-line'], map);
```

**CRITICAL — Fix beforeId dependency:** The `parcel-line` layer (line 364) uses
`'pourpoint-line'` as its `beforeId` parameter. After removing pourpoint-line,
this reference must be updated or parcel-line will throw an error on load:
```javascript
// Before:
map.addLayer({ id: 'parcel-line', ... }, 'pourpoint-line');
// After:
map.addLayer({ id: 'parcel-line', ... }, 'aoi-2km-line');
```

**Step 4: Remove reachability indicator (line 104)**

Delete:
```html
<div class="stat"><span class="stat-label" style="color:#d2991d;font-weight:600;">⇢ De Anza Villas only</span></div>
```

**Step 5: Revert stat label (line 103)**

Change:
```html
<div class="stat"><span class="stat-label">Reachable cells</span>…</div>
```
to:
```html
<div class="stat"><span class="stat-label">Stream cells</span>…</div>
```

**Step 6: Update legend label (line 50)**

Change "Watershed boundary (107 km²)" to "Parcel contributing area".

**Step 7: Update title (line 6)**

Change "Henderson Canyon Watershed (107 km²)" to "De Anza Villas Flood Study".

**Step 8: Copy boundary to maps/**

```bash
cp data/derived/vectors/deanza_parcel_contributing_area.geojson outputs/maps/
```

**Step 9: Commit**

```bash
git add outputs/maps/stream_explorer.html \
        outputs/maps/deanza_parcel_contributing_area.geojson
git commit -m "feat: stream explorer uses parcel contributing area"
```

---

### Task 5: Full pipeline regeneration

**Objective:** Run all four build functions on the new contributing area extent.

**Prerequisites:** Tasks 1–4 committed. All deps in venv.

**Step 1: Backup existing files**

```bash
mkdir -p /tmp/flood-study-backup-$(date +%Y%m%d)
cp -r data/derived/henderson/*.tif /tmp/flood-study-backup-$(date +%Y%m%d)/
cp outputs/maps/streams_*.bin /tmp/flood-study-backup-$(date +%Y%m%d)/
# Keep this backup at least a week. Old binaries are cheap insurance against
# needing to re-run the 1m D8 accumulation from scratch.
```

**Step 2: Clear old rasters**

```bash
cd /home/hermes/workspace/deanza-villas-flood-study
rm -f data/derived/henderson/dem_1m_filled_f32.tif
rm -f data/derived/henderson/dem_1m_clipped.tif
rm -f data/derived/henderson/d8_pointer_1m.tif
rm -f data/derived/henderson/d8_flow_accum_1m*.tif
rm -f data/derived/henderson/streams_d8_1m_250*.tif
rm -f data/derived/henderson/dinf_pointer_1m.tif
rm -f data/derived/henderson/dinf_flow_accum_1m*.tif
rm -f data/derived/henderson/streams_dinf_1m_250*.tif
rm -f outputs/maps/streams_d8_1m.bin outputs/maps/streams_all.bin
```

**Step 3: Run 1m builds**

```bash
# D∞ first (WBT-native, low memory)
OMP_NUM_THREADS=4 .venv/bin/python -m deliverable._henderson dinf1m

# D8 second (pyflwdir, higher memory)
OMP_NUM_THREADS=4 .venv/bin/python -m deliverable._henderson d81m
```

Monitor with `htop`. Expected peak RSS ~2 GB for D∞, ~3–4 GB for D8.
If D8 OOMs, use multi-process fallback:
```bash
OMP_NUM_THREADS=4 .venv/bin/python spikes/process_a_d8_accum.py
OMP_NUM_THREADS=4 .venv/bin/python spikes/process_b_streams.py
# Manual binary export (no reachability needed)
.venv/bin/python -c "
from deliverable._henderson import _export_binary
from pathlib import Path
H = Path('data/derived/henderson')
M = Path('outputs/maps')
_export_binary(H / 'streams_d8_1m_250.tif',
               H / 'd8_flow_accum_1m_masked.tif',
               M / 'streams_d8_1m.bin',
               boundary=Path('data/derived/vectors/deanza_parcel_contributing_area.geojson'))
"
```

**Step 4: Run 10m builds**

```bash
.venv/bin/python -m deliverable._henderson d810m
.venv/bin/python -m deliverable._henderson dinf10m
```

**Step 5: Verify**

```bash
.venv/bin/python -c "
import struct, rasterio, numpy as np

# D8 monotonicity
acc = rasterio.open('data/derived/henderson/d8_flow_accum_1m_masked.tif').read(1)
ptr = rasterio.open('data/derived/henderson/d8_pointer_1m.tif').read(1)
D8 = {1:(-1,1),2:(0,1),4:(1,1),8:(1,0),16:(1,-1),32:(0,-1),64:(-1,-1),128:(-1,0)}
nonzero = np.argwhere(ptr > 0)
n = min(500, len(nonzero))
idxs = np.random.choice(len(nonzero), n, replace=False)
v = 0
for i in idxs:
    r,c = nonzero[i]
    p = int(ptr[r,c])
    if p in D8:
        dr,dc = D8[p]; nr,nc = r+dr,c+dc
        if 0 <= nr < ptr.shape[0] and 0 <= nc < ptr.shape[1]:
            if acc[r,c] > acc[nr,nc]: v += 1
print(f'D8 monotonicity: {v}/{n} violations' + (' ✓' if v==0 else ' FAIL'))

# Binary size checks
for f, name in [('outputs/maps/streams_d8_1m.bin','D8 1m'),
                 ('outputs/maps/streams_all.bin','D∞ 1m')]:
    with open(f,'rb') as fh:
        n = struct.unpack('I',fh.read(4))[0]
    import os; sz = os.path.getsize(f)
    ok = '✓' if sz == 4+n*12 else 'FAIL'
    print(f'{name} binary: {n:,} cells, {sz:,} bytes {ok}')
"
```

Checklist after verification:
- [ ] D8 accum monotonic (0 violations)
- [ ] Both binaries have correct size (header + N×12)
- [ ] Stream cell counts are plausible for contributing area size
- [ ] No inf/nan in binary
- [ ] Contributing area is a strict subset of old Henderson 33.6 km² polygon
      (overlay both in QGIS or check bounds: new area w/in old bounds)

**Step 5b: Verify reachability is a near-no-op**

The assertion that all streams reach the parcel by construction must be tested,
not assumed. The contributing area was traced on the OLD pointer; streams are
extracted from the NEW (re-clipped) pointer. Edge effects and breach/fill
differences can create stream cells inside the polygon that route to the edge.

```bash
.venv/bin/python -c "
from deliverable.reachability import filter_reachable
from deliverable._henderson import PARCEL
from pathlib import Path
H = Path('data/derived/henderson')

# D8 1m
result = filter_reachable(
    H / 'streams_d8_1m_250.tif',
    H / 'd8_pointer_1m.tif',
    PARCEL,
    output=H / '_verify_reachable_d8.tif',
    pointer_type='d8')
print()

# D∞ 1m
result = filter_reachable(
    H / 'streams_dinf_1m_250.tif',
    H / 'dinf_pointer_1m.tif',
    PARCEL,
    output=H / '_verify_reachable_dinf.tif',
    pointer_type='dinf')
print()

# Cleanup verification files
Path(H / '_verify_reachable_d8.tif').unlink()
Path(H / '_verify_reachable_dinf.tif').unlink()
"
```

If either reports < 0.1% of cells NOT reaching the parcel, the pipeline needs
the reachability filter after all. If 99.9%+ reach (expected), skip it.

**Step 6: Test web explorer**

```bash
# Start dev server if not running
ss -tlnp | grep 8765 || \
  .venv/bin/python -m http.server 8765 --directory outputs/maps &
```

Open `http://localhost:8765/stream_explorer.html` and verify:
- [ ] Map loads with new boundary polygon
- [ ] D∞ 1m default, cells visible at threshold 1000
- [ ] Dataset buttons switch correctly
- [ ] Slider adjusts visible cells
- [ ] No community bbox toggle
- [ ] No reachability indicator
- [ ] Stat shows "Stream cells" with correct count

**Step 7: Commit**

```bash
git add -A
git commit -m "feat: regenerate pipeline on parcel contributing area"
```

---

### Task 6: Cleanup stale files

**Step 1: Delete old boundary and community bbox**

```bash
rm -f data/derived/vectors/henderson_watershed_boundary.geojson
rm -f data/derived/vectors/henderson_watershed_boundary_5070.geojson
rm -f data/derived/vectors/henderson_watershed_boundary_WRONG_107km2.geojson
rm -f outputs/maps/deanza_community_bbox.geojson
```

**Step 2: Commit**

```bash
git add -A
git commit -m "chore: remove stale community bbox and old watershed boundary"
```

---

## Verification Gates (end-to-end)

```bash
cd /home/hermes/workspace/deanza-villas-flood-study

# 1. All canonical files present
python3 -c "
from pathlib import Path
for f in [
    'deliverable/upstream.py',
    'data/derived/vectors/deanza_parcel_contributing_area.geojson',
    'data/derived/vectors/deanza_parcel_contributing_area_5070.geojson',
    'outputs/maps/streams_d8_1m.bin',
    'outputs/maps/streams_all.bin',
    'outputs/maps/deanza_parcel_contributing_area.geojson',
]:
    p = Path(f)
    assert p.exists(), f'MISSING: {f}'
    print(f'  OK  {f}')
print('All files present.')
"

# 2. No stale references
grep -rn "community_bbox\|henderson_watershed_boundary" \
  outputs/maps/stream_explorer.html deliverable/_henderson.py \
  && echo "STALE REFERENCES FOUND — CHECK ABOVE" \
  || echo "No stale references — OK"

# 3. pyflakes clean
.venv/bin/python -m pyflakes deliverable/upstream.py deliverable/_henderson.py \
  && echo "pyflakes clean — OK"

# 4. Web server running
ss -tlnp | grep -q 8765 && echo "Server on :8765 — OK" \
  || echo "SERVER NOT RUNNING — start: python -m http.server 8765"
```

---

## Risks

| Risk | Mitigation |
|------|-----------|
| Contributing area touches pointer edge (upstream extends beyond current grid) | edge_check warns. If triggered, fetch wider DEM via fetch_dem with larger buffer_m. Unlikely — parcel is inside community, community's area already fits. |
| D8 1m build OOMs in single process | Fall back to multi-process spike scripts. Contributing area is smaller than old watershed → inherently less memory pressure. |
| Contributing area < 1 km² (parcel on minor distributary) | Inspect result visually. If too small, discuss reverting to full Henderson watershed. Mitigant: the contributing area from even a small parcel on an alluvial fan can extend far up-canyon through the main channel. |
| Contributing area is wrong basin (parcel in closed depression) | Validate by overlaying on the original 33.6 km² Henderson polygon in QGIS. New area must be a strict subset. If it's a tiny disconnected blob on the fan surface, the parcel's drainage doesn't connect to the canyon — reachability filter is essential. Don't delete old boundary files until this is confirmed. |
| D∞ upstream trace is slow on 107M-cell pointer | BFS visits each cell once. ~107M cells ÷ ~250K/s ≈ 7 minutes. Acceptable for one-shot. Trace runs on existing pointer — no DEM recompute needed. |
| 10m builds reference `watershed_wide.tif` | Fixed in Task 3: all builds now rasterize the boundary polygon directly, matching 1m pattern. |
| Binary files larger (all streams vs reachable subset) | Full-stream binaries 50–100 MB at 1m. fetch-on-load pattern handles this. Loading spinner provides feedback. |
