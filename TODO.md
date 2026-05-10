# TODO.md — Parcel-Centered Pipeline Cleanup

Clean up the partial consolidation and restore a consistent parcel-centered pipeline.

## Background

The consolidation plan (`outputs/reports/parcel_consolidation_plan.md`) was partially executed
by a prior session then partially walked back. The code is in a hybrid state: some functions
use CONTRIBUTING_AREA, some use HENDERSON, old Henderson Canyon naming persists in file paths.

**Goal:** consistent parcel-centered pipeline. Everything drains from the parcel, nothing
references Henderson Canyon by name.

**Key rule for this work:** do NOT encode computation results (area numbers, cell counts,
percentages, file sizes, timing) in skill, memory, or TODO.md. These change when input changes.
Describe what to do, not what the answer should be.

## Task 1: Rename away from Henderson ✅ (completed 2026-05-09)

- Rename `data/derived/henderson/` → `data/derived/watershed/`
- Rename `deliverable/_henderson.py` → `deliverable/_pipeline.py`
- Find and update ALL references to these paths across the repo:
  - `_henderson` → `_pipeline` in imports, CLI invocations, config, documentation
  - `data/derived/henderson` → `data/derived/watershed` in all files
- Update `.gitignore` to match new path
- Commit: "refactor: rename Henderson paths to watershed"

## Task 2: Revert _pipeline.py to clean parcel-centered state ✅ (completed 2026-05-09)

Current state of `_pipeline.py` (formerly `_henderson.py`):
- Has both HENDERSON and CONTRIBUTING_AREA constants (hybrid)
- Some build functions use HENDERSON for DEM fetch, some use CONTRIBUTING_AREA
- Missing imports from Task 3 removals were partially re-added
- D8/D∞ tolerance widened to 0.50

Target state:
- Single boundary constant: `CONTRIBUTING_AREA` (parcel contributing area)
- Remove `HENDERSON` constant entirely
- All build functions fetch and mask to CONTRIBUTING_AREA
- Keep reachability filter (`filter_reachable`) as a generic self-consistency step
  — it answers the question "do extracted streams actually reach the parcel?"
- Keep `_mask_to_boundary` helper (already present from prior Task 3)
- Remove `build_watershed_boundary()` if still present
- Remove `delineate_watershed` import if still present
- Keep widened D8/D∞ tolerance (0.50) — fan divergence is real
- Remove "watershed" command from `__main__` block
- Update docstrings to remove Henderson references

## Task 3: Update stream explorer ✅ (completed 2026-05-09)

File: `outputs/maps/stream_explorer.html`
- Remove Henderson watershed boundary layer (source, layer, legend toggle, fetch, toggle binding)
- Remove any remaining pour-point / community bbox references if present
- Verify no `beforeId` dependencies break when removing Henderson layer
- Update legend label for contributing area to just say "Parcel contributing area"
  (drop the area number from the label — it's a computation result)

## Task 4: Full pipeline regeneration ✅ (completed 2026-05-09)

Clear old outputs and regenerate everything on the parcel contributing area extent:

```bash
# Clear old 1m rasters
rm -f data/derived/watershed/dem_1m_*.tif
rm -f data/derived/watershed/d8_*.tif
rm -f data/derived/watershed/dinf_*.tif
rm -f data/derived/watershed/streams_*.tif

# Regenerate
.venv/bin/python -m deliverable._pipeline dinf1m
.venv/bin/python -m deliverable._pipeline d81m
.venv/bin/python -m deliverable._pipeline dinf10m
.venv/bin/python -m deliverable._pipeline d810m
```

Verify after regeneration:
- D8 accumulation monotonic (0 violations on random sample)
- Binary files have correct format (header + N×12 bytes)
- Both 1m and 10m binaries exist
- Stream explorer loads and renders cells

## Task 5: Clean up stale files ✅ (completed 2026-05-09)

Remove files from the old community-bbox / Henderson era:
- `outputs/maps/deanza_community_bbox.geojson`
- `outputs/maps/henderson_watershed_boundary.geojson`
- `data/derived/vectors/henderson_watershed_boundary.geojson`
- `data/derived/vectors/henderson_watershed_boundary_5070.geojson`
- Any other files referencing Henderson or community_bbox in outputs/maps/

Commit each task separately.

## Guidance

- **Regeneration requires approval.** Never run `_pipeline` commands without user go-ahead.
- **Don't encode results.** The plan describes what to do and how to verify, not what
  numbers to expect. The computation speaks for itself.
- **Trust the computation.** If the contributing area is smaller than intuition suggests,
  verify with diagnostics (downstream transect, raw DEM comparison, multi-resolution check)
  but accept the answer.
- **Reachability filter is generic.** It's not "this parcel needs it." It's a self-consistency
  check for any pipeline run — answers whether extracted streams route to the target.
