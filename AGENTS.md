# AGENTS.md

Fast entry point for agents working in this repository.

## What this repo is

Borrego Springs / De Anza Villas flood study. Geospatial, terrain-driven.
Centered on a parcel boundary, a contributing area, and a stream morphology
explorer. The active parcel is set in `deliverable/_pipeline.py`.

## Project layout

```
deliverable/          Portable DEM/hydrology library + project pipeline
  _pipeline.py        Project CLI — fetch, preprocess, flow, streams, export
  parcels.py          Parcel boundary generators (De Anza Villas, Country Club)
  fetch.py            USGS TNM DEM fetch (1m + 10m)
  preprocess.py       DEM conditioning (breach + fill)
  d8.py / dinf.py     Flow direction + accumulation
  streams.py          Stream extraction + export
  reachability.py     Optional reachability filter
  verify.py           Accumulation sanity checks

scripts/              One-off data fetch scripts (run with python -m scripts.<name>)
  fetch_parcel_deanza_villas.py
  fetch_parcel_deanza_country_club.py
  fetch_fema.py
  fetch_huc12.py

data/raw/vectors/     Source vector data — fetched on demand, not committed
data/raw/dem/tiles/   Cached DEM tiles — not committed
data/derived/rasters/ Computed rasters — cleaned by pipeline clean
data/derived/vectors/ Computed vectors — cleaned by pipeline clean
outputs/maps/         Stream explorer (index.html) + GeoJSON/binary assets
```

## Running the pipeline

```bash
# From project root, with .venv activated:
python -m deliverable._pipeline prepare        # fetch parcel + contributing area
python -m deliverable._pipeline dinf1m         # D∞ 1m streams
python -m deliverable._pipeline dinf10m
python -m deliverable._pipeline d81m
python -m deliverable._pipeline d810m
python -m deliverable._pipeline all            # prepare + all four
python -m deliverable._pipeline clean          # delete derived artifacts
python -m deliverable._pipeline clean-all      # also delete DEM tile cache
```

## Key conventions

- Active parcel: set `PARCEL` path and `parcel_fn` default in `_pipeline.py`
- CRS: EPSG:5070 (Albers Equal Area) throughout; EPSG:4326 for GeoJSON output
- DEM tiles are cached in `data/raw/dem/tiles/` — never deleted by `clean`
- Raw vector inputs live in `data/raw/vectors/` — never deleted by `clean`
- `prepare()` calls `parcel_fn(PARCEL)` if boundary missing — generates on demand
- Stream binaries: `dinf_1m.bin`, `dinf_10m.bin`, `d8_1m.bin`, `d8_10m.bin`

## Known non-obvious invariants (hard-won)

### D∞ accumulation: always pass `out_type="cells"`
WBT `d_inf_flow_accumulation` defaults to SCA (specific catchment area, m²/m),
not cell count. On fan terrain, noisy flow angles → contour width → 0 →
division overflow → inf. Always pass `out_type="cells"`. `verify_accumulation()`
catches SCA mode: `nonzero_min == cell_width_in_meters` means you're in SCA mode.

### WBT D8 accumulation hangs on WBT 2.3.6
`d8_flow_accumulation` runs indefinitely on large rasters. Cause unknown — not
memory, not nodata, not cycles. Fix: compute pointer with WBT, accumulate with
`pyflwdir.from_array(ptr, ftype='d8', check_ftype=False)`. If upgrading WBT,
retest D8 accumulation before removing the `wbt_ptr_pyflwdir` backend.

### Never use `pyflwdir.from_dem` — use `from_array` with WBT pointer
`from_dem` refills depressions using Wang & Liu 2006, connecting sub-basins
that WBT's breaching keeps separate. Produces accumulation ~3.37× higher than
D∞. Always use `from_array` with a WBT-computed pointer.

### Mask D8 pointer nodata to 0 before pyflwdir
WBT writes nodata as -32768 (int16). pyflwdir treats -32768 as a flow
direction and corrupts accumulation. `d8.py` masks automatically:
`ptr_data[~valid_mask] = 0`.

### `rasterio.warp.transform` returns lists, not arrays
Indexing Python lists with boolean masks or argsort produces wrong results
silently. Always wrap: `lons = np.asarray(lons)`. `_export_binary()` does this.

### `features.shapes` / `features.rasterize` require int16 value + uint8 mask
Passing uint8 for both corrupts edge cells by 1-2 pixels. Cast value array to
int16, mask to uint8. Affects pour-point rasterization and polygonization in
`upstream.py`.

### WBT paths must be absolute
WBT silently produces no output for relative paths. Always pass
`str(Path(p).resolve())`. The library does this internally.

### Breach then fill, not fill-only, for alluvial fan terrain
Fill-only creates artificial flats that block D8 routing. On Henderson Canyon,
fill-only produced 0% FEMA hazard overlap; breach+fill produced 72%.
`preprocess_dem()` defaults to `breach_then_fill`.

### All overlapping 1m tile surveys must be fetched, not just the newest
TNM returns multiple surveys per grid position. "CaliforniaGaps" tiles have
holes in steep terrain (canyons). `_query_tnm` returns all surveys
newest-first; `rio_merge(method='first')` uses newest where available and
falls back to older surveys to fill gaps. Do not re-introduce per-position
deduplication.

### Reachability filter is wrong for alluvial fan terrain
D8/D∞ pointers on nearly flat fan terrain route flow arbitrarily and often
miss the parcel polygon entirely. Default `reachability_mode='none'` — export
all streams within the CA. Use `--reachability boolean` only when the parcel
sits in a clear channel, not on a fan.

### WBT fill_depressions writes float64 uncompressed
Output is ~3× larger than expected. `compute_dinf()` recompresses to
float32+LZW after WBT writes.

### WBT set_verbose_mode(False) prevents pipe stalls
On large rasters, WBT progress output fills the pipe buffer and stalls the
parent. Always call `set_verbose_mode(False)`.
