# TODO.md

Use this file as the queued-pending work list for the current effort.

Suggested format:
- Keep items short and ordered by priority.
- Use checkboxes or a simple backlog list.
- Mark items `in_progress` while working on them. When done, remove them — `DEVLOG.md` records the outcome.
- Add or reconcile items when the same request comes up again.

Recommended relationship to other repo logs:
- `DEVLOG.md` = what actually happened, with short timestamped notes
- `TODO.md` = what is queued or pending (not an archive of completed work)
- `CHANGELOG.md` = public release/history notes, if the project uses one

## Backlog

- in_progress: 2D rain-on-grid (REFACTOR_PLAN "Future areas of study" §1)
  - Fix steep-chute surges in the scheme (blocks 4 m as the official grid, and any 2/1 m run). At θ = 1 they don't shrink with Δt (4 m, CFL 0.3/0.15/0.075: ~1,000 cells >20 m/s, top ~75–80 m/s; 20–30% of steep cells' max depth moves >10%). Options: apply the θ-smoothing at a fixed rate per second instead of per step (so it doesn't depend on Δt), or a shock-capturing solver for supercritical flow. Re-run the 8 m / 4 m CFL checks and the LFP 8 m comparison after. See DEVLOG 2026-09-25
  - Spatially varying Manning's n (steep boulder channels ~0.07–0.15; 0.045 gives ~11 m/s at 1 m depth)
  - Optional: extend the LFP diffusive 8 m check past 45 min to cover the parcel's peak (hours of wall time)
  - Finer grids: 2 m and 1 m Villas runs; grid-convergence check
  - Storm sensitivity: 6-h and 24-h durations, peak position, 25/500-year
  - Check the deep channel south of the Villas (4 m modelled) against imagery / County flood-control works
  - Country Club domain (40 km², coarser grid) — does fan flow from outside the Villas' traced area reach the Villas?
  - Loss (infiltration) sensitivity; burn in buildings/walls (bare-earth lidar has none)
  - Publish depth maps to the explorer
- Graceful failure on empty/nodata/ridge contributing area (pipeline crashes mid-flow-accumulation rather than reporting a clean error)
- Test pipeline on substantially different terrain (Appalachians, karst, glacial) — Jacksonville coastal plain is benign
- Consider `BreachDepressionsLeastCost` with max breach length as middle-ground hydro strategy (between aggressive breach_then_fill and conservative fill_only)
- Flow-weighted cycle propagation mask: track all cells affected by cycle-truncated branches (currently only logs origination count)
- Explorer slider adaptation for flow-weighted binaries: read value-space flag from header, adjust slider labels and scale accordingly
