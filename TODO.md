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

- in_progress: 2D rain-on-grid (REFACTOR_PLAN "Future areas of study" §1). 8 m is official; the parcel answer has held within ~10% across every numerics change, so input uncertainty now outweighs the numerics (DEVLOG 2026-09-25)
  1. Sensitivity batch at 8 m, run in parallel on Modal (~1 min each): losses (initial + constant rate), Manning's n (incl. rougher channels ~0.07–0.15), storm length 1/6/24 h, 25/100/500-year, peak position. Output: one table of parcel/Zone A/outside-SFHA stats per case
  2. Burn in buildings/walls (bare-earth lidar has none); likely matters more at parcel scale than solver choice
  3. Publish 8 m depth maps to the explorer
  4. Check the deep channel south of the Villas against imagery / County flood-control works
  5. Country Club domain (40 km², coarser grid): does fan flow from outside the Villas' traced area reach the Villas?
  - Parked (only if a decision needs chute-level detail or <8 m grids):
    - Steep-chute surges at ≤4 m: at θ = 1 they don't shrink with Δt (4 m, CFL 0.3/0.15/0.075: ~1,000 cells >20 m/s, top ~75–80 m/s). Try an existing solver built for steep, fast flow (ANUGA; FLO-2D is the FEMA alluvial-fan standard) before patching ours (θ-smoothing per second rather than per step)
    - Finer grids (4/2/1 m) and a grid-convergence check; blocked on the surges
    - Extend the LFP diffusive 8 m check past 45 min to cover the parcel's peak (hours of wall time)
- Graceful failure on empty/nodata/ridge contributing area (pipeline crashes mid-flow-accumulation rather than reporting a clean error)
- Test pipeline on substantially different terrain (Appalachians, karst, glacial) — Jacksonville coastal plain is benign
- Consider `BreachDepressionsLeastCost` with max breach length as middle-ground hydro strategy (between aggressive breach_then_fill and conservative fill_only)
- Flow-weighted cycle propagation mask: track all cells affected by cycle-truncated branches (currently only logs origination count)
- Explorer slider adaptation for flow-weighted binaries: read value-space flag from header, adjust slider labels and scale accordingly
