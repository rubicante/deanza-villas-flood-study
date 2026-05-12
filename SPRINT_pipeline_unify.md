# Sprint: Unify pipeline — eliminate bootstrap.py

## Goal

All orchestration lives in `deliverable/_pipeline.py`. `scripts/bootstrap.py` is deleted.
The large 10m fetch is a temporary superset used only to establish the contributing area;
tile caching means subsequent `fetch_10m(ca)` calls for analysis hit the cache with no
re-download. No new clipping logic needed.

## Full pipeline sequence

```
prepare:
  fetch_10m(parcel + 25km buffer)   ← large temporary superset, tiles cached
  preprocess_10m
  dinf_ptr_10m
  contributing_area BFS
  save CA GeoJSONs
  delete superset intermediates (dem, filled, ptr)

all:
  prepare
  dinf1m:  fetch_1m(ca) → preprocess → dinf_ptr → accum → streams → reachable → binary
  d81m:    fetch_1m(ca) → (reuse filled_1m) → d8_ptr → accum → streams → reachable → binary
  dinf10m: fetch_10m(ca) → preprocess → dinf_ptr → accum → streams → reachable → binary
  d810m:   fetch_10m(ca) → (reuse filled_10m) → d8_ptr → accum → streams → reachable → binary
```

Note: `dinf1m` and `d81m` share the same filled 1m DEM; `dinf10m` and `d810m` share the
same filled 10m DEM (CA-bounded). Tile downloads hit cache from the prepare step.

## Changes

### `deliverable/_pipeline.py`

- Add constants: `PARCEL`, `BOOTSTRAP_BUFFER_M = 25_000.0`
- Add import: `from deliverable.upstream import contributing_area`
- Add `prepare()` function encapsulating the contributing area computation + cleanup
- Add `prepare` CLI subcommand
- Update `all` command to call `prepare()` then the four build variants
- Remove the `if not dem_filled.exists()` guard in `build()` — steps are idempotent
  via WBT overwriting; or keep the guard but base it on the final binary output

### `scripts/bootstrap.py`

- Delete entirely

### Cleanup

- Delete `SPRINT_fetch_dem.md` (superseded by this sprint)
- Delete this file when sprint is complete

## What does NOT change

- `build()` signature and internals — no clipping logic added
- `fetch_dem_1m` / `fetch_dem_10m` — unchanged
- Tile cache location — 10m CA tiles already present from prepare step
- All output file names — dinf_ptr_10m, dem_10m_clipped, etc. stay as-is
