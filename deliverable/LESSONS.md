# Spike Lessons — Henderson Canyon Watershed (May 2026)

Each entry documents a failure mode encountered during the build, the
diagnosis, and the fix encoded in the `deliverable/` library.

## D∞ `out_type` default is SCA, not cells

**Symptom**: D∞ accumulation has nonzero_min = cell width (m), max = infinity
(435K inf cells on 165M px DEM). Streams at threshold 250 are inflated (1.2M
cells) and dominated by inf-valued channel cores.

**Cause**: WBT `d8_flow_accumulation` defaults to `out_type="cells"` but
`d_inf_flow_accumulation` defaults to `out_type="specific catchment area"`
(SCA, units m²/m). SCA divides accumulated area by contour width. On the
alluvial fan, noisy D∞ flow angles land near cell edges where contour
width approaches zero → division overflow → float64 inf.

**Fix**: Always pass `out_type="cells"` explicitly to `d_inf_flow_accumulation`.
The deliverable never omits this parameter. `verify_accumulation()` catches SCA
mode by checking `nonzero_min == 1.0` (SCA mode would show nonzero_min == cell
width).

**Diagnostic**: If `nonzero_min == cell_width_in_meters`, you're in SCA mode.

## WBT `fill_depressions` writes float64 uncompressed

**Symptom**: Filled DEM is 1,318 MB on disk (float64) vs 437 MB expected
(float32+LZW). This doubles downstream memory for D∞ which internally upcasts
to float64 anyway.

**Cause**: WBT writes float64 by default. The `fetch_dem()` function returns
float32+LZW but `fill_depressions` silently changes the output format.

**Fix**: `compute_dinf()` compresses output back to float32+LZW. The library
also stores intermediate filled DEMs as float32+LZW when possible.

## D8 accumulation hangs on WBT 2.3.6

**Symptom**: WBT `d8_flow_accumulation` runs indefinitely (12+ minutes with no
output) on 165M px raster with nodata borders. Tested on sizes from 200×200
to 16,736×9,847 — hangs at all sizes. D8 pointer computes in 14s; only
accumulation hangs. Memory is not the issue (swap enabled, parent RSS freed,
D∞ at 1m succeeds on same DEM in 24s).

**Cause**: Unknown. Not cycles (masked pointer to pure {0,1,2,4,8,16,32,64,128}
still hangs). Not nodata values (removed -32768). Not memory (1000×1000
no-nodata window also hangs). Likely a WBT binary bug.

**Fix**: WBT `d8_pointer` works (14s), so compute pointer with WBT, then
accumulate with `pyflwdir.from_array(ptr, ftype='d8', check_ftype=False)`.
pyflwdir must NOT refill (skip `from_dem` — use `from_array` with the WBT
pointer directly). `d8.py` exposes this as the `wbt_ptr_pyflwdir` backend.

**If upgrading WBT**: Retest D8 accumulation. If it works, the `auto` backend
in `d8.py` will prefer it. If the pointer encoding or format changes, the
`wbt_ptr_pyflwdir` backend may break silently — diff outputs.

## pyflwdir `from_dem` refills and inflates accumulation by 3.37×

**Symptom**: `pyflwdir.from_dem()` on a WBT-filled DEM produces D8
accumulation 3.37× higher than WBT D∞. The fill algorithm (Wang & Liu 2006)
connects sub-basins that WBT's breaching keeps separate.

**Fix**: Never use `from_dem`. Use `from_array(ptr, ftype='d8', check_ftype=False)`
with a WBT-computed pointer. The `check_ftype=False` is required — pyflwdir's
D8 validation rejects WBT pointers (likely due to intra-array zero/sink cells).

## Mask pointer nodata to 0 before accumulation

**Symptom**: WBT `d8_pointer` writes nodata cells as -32768 (int16 dtype).
Passing this pointer to pyflwdir `from_array` without masking causes
accumulation to treat -32768 as a flow direction (wraps/corrupts).

**Fix**: Set all nodata cells in the pointer to 0 (sink) before passing to
pyflwdir. `d8.py` does this automatically: `ptr_data[~valid_mask] = 0`.

## Single target grid prevents merge-time seams

**Symptom**: Reprojecting each py3dep tile to its own independent `from_origin`
transform produces sub-pixel misalignment at tile boundaries after merge.
`rasterio.merge` resamples to reconcile the misaligned grids, producing subtle
seam artifacts.

**Fix**: Compute a single global transform snapped to the target resolution
from the buffered bbox. Reproject every tile into that same grid. Clip each
tile to the buffered polygon BEFORE merging — eliminates nodata padding and
prevents WBT from processing no-data cells.

## WBT paths must be absolute

**Symptom**: WBT methods sometimes fail silently when given relative paths —
no output file, no error message.

**Fix**: Always pass `str(Path(path).resolve())` to all WBT methods. The
library does this internally; callers never need to.

## rasterio.warp.transform returns Python lists

**Symptom**: `rasterio.warp.transform(src_crs, dst_crs, xs, ys)` returns
Python lists, not numpy arrays. Indexing with boolean masks or argsort on
lists silently produces wrong results. Caused silent data corruption in
binary exports during initial spike builds.

**Fix**: Always wrap with `np.asarray()`.
`_export_binary()` does: `lons = np.asarray(lons); lats = np.asarray(lats)`.

## WBT set_verbose_mode(False) prevents pipe stalls

**Symptom**: On large rasters (>100M px), WBT's progress output fills the
pipe buffer and stalls the parent process, appearing as a hang.

**Fix**: `set_verbose_mode(False)` on all WBT calls. The library does this.


## rasterio `features.shapes` and `features.rasterize` require int16 raster + uint8 mask

**Symptom**: `features.shapes(binary, mask=mask)` with both arguments as uint8
produces wrong polygon boundaries — edges drift from the true watershed mask
by 1-2 pixels. Same failure in `features.rasterize()` when creating pour-point
rasters from geometry: wrong cell assignments at polygon edges.

**Cause**: rasterio's Cython-level dtype dispatch treats int16 and uint8
differently for mask handling. uint8 mask triggers a code path that correctly
respects the mask boundary; uint8 raster + uint8 mask follows a different
path that corrupts edge cells.

**Fix**: Always pass `binary.astype("int16")` for the value array and
`mask=mask.astype("uint8")` for the mask, in both `shapes()` and `rasterize()`.

**Affected**: `delineate_watershed()` does this in both pour-point rasterization
and polygonization steps. External callers using raw rasterio need the same pattern.

## Breach then fill, not fill-only, for alluvial fans

**Symptom**: `fill_depressions` alone on alluvial fan terrain creates
artificial flats that block D8 routing. On Henderson Canyon, fill-only
produced 0% FEMA hazard overlap at threshold 5000; breach+fill produced 72%.

**Fix**: `preprocess_dem()` defaults to `strategy='breach_then_fill'` with
`breach_max_length=250`. Expose `strategy` parameter because other terrains
(glaciated, coastal plain) may need different handling.

## D∞ at 1m on 165M px needs ~4.7 GB RSS

**Symptom**: WBT D∞ at 1m on 165M px float32 DEM was killed on 7.6 GB RAM
with no swap. D∞ internally upcasts to float64: three arrays at
164.8M × 8 bytes = 3,957 MB plus DEM mmap and buffers = ~4.7 GB total.

**Fix**: Enable swap (8 GB was sufficient for the deficit). On systems with
more RAM, this is a non-issue. The library does NOT enforce a pixel-count
guard — the limit is hardware-specific and the right behavior is to let WBT
fail and surface the error.

## The pipe `&` heredoc bug

**Symptom**: Terminal heredocs containing `&` (common in numpy boolean
masking: `(mask > 0) & (dem > 250)`) fail with "Foreground command uses '&'
backgrounding."

**Fix**: Use `write_file` for Python scripts, then `terminal(command="python script.py")`.
Not a library issue, but documented here because it cost debugging time.
