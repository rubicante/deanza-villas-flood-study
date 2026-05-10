# Project Plan — Parcel-Centered Flood Study Pipeline

*Derived from pipeline review 2026-05-09. Ordered by priority for "works on arbitrary parcels" goal.*

---

## Phase 1 — Correctness (D∞ reachability memo bug)

**Problem:** The D∞ reachability filter can permanently cache `False` for cells whose
only proof of non-reachability was hitting a cycle in one branch of a multi-branch
trace. If a different upstream cell later queries that cached cell, it gets a false
negative even though the cell might reach the target via a different branch.

**Root cause:** The post-order DFS writes `cache[cell] = 2` when a trace short-circuits
on the per-trace `visited` set. For D8 (single downstream neighbor) this is correct —
if the only path hits a cycle, the cell truly doesn't reach. For D∞ (Tarboton
two-neighbor routing), a cell may have one neighbor in a cycle and another that
reaches the target. The cycle-determined False is path-specific, not a general truth
about the cell.

**Three constructed test cases needed:**

1. **Cycle with no exit.** A→B→C→B. Nothing reaches target. All three resolve False,
   all safe to cache. (No path ambiguity — the cycle IS the whole story.)

2. **Cycle plus alternate path.** A→{B, C}; B→D→B (cycle); C→target. A should
   resolve True regardless of DFS child visit order. B and D resolve False but
   their False is cycle-determined — should NOT be cached because a different
   upstream cell routing into D via a non-cyclic path shouldn't inherit a
   cached False.

3. **Cell upstream of a cycle, no other exit.** A→B→C→D→C (cycle on C/D). A and B
   have only the cycle as exit — their False is correct and cacheable. C and D's
   False is cycle-determined — should NOT be cached.

**Fix approach:** Tag False results with whether they were cycle-determined.
Propagate the tag up through the OR in post-order resolution. Only commit to the
shared cache when the result is no longer cycle-tagged (i.e., some sibling branch
resolved cleanly, or we're at a cell where the cycle is the only downstream option
and the cell itself has no alternate branches).

**Verification:** Test-first. Write the three constructed grids, assert expected
reachability, assert cache entries are correct. Run against current implementation
(should fail on cases 2 and 3), then implement fix (should pass all three).

**Files:** `deliverable/reachability.py` (fix), new test file.

---

## Phase 2 — Generalize threshold and parameters

### 2a. Accumulation threshold as fraction of contributing area

**Problem:** A fixed threshold of 250 cells works for a 0.4 km² parcel but produces
nothing on a 0.05 km² parcel and a dense mat on a 5 km² parcel. The threshold
should scale with contributing area size.

**Fix:** Accept threshold as fraction of total contributing cells (e.g., 250 /
N_contributing_cells). Convert back to absolute cell count internally for WBT
`extract_streams`. Default: a fraction that approximates the current 250-cell
behavior on the test parcel, with override via CLI parameter.

**Files:** `deliverable/_pipeline.py` (all four build functions), `__main__` block.

### 2b. Parcel buffer parameter

**Problem:** The 3m buffer for upstream tracing and reachability is hardcoded.
Different parcel data sources have different positional accuracies (county GIS ±1m
to ±5m, hand-drawn boundaries potentially more). A fixed 3m will silently miss
streams on imprecise boundaries.

**Fix:** Expose `buffer_m` as a parameter with default 3m. Document what it
protects against (registration tolerance between parcel boundary and DEM).

**Files:** `deliverable/upstream.py`, `deliverable/reachability.py` (already
parameterized), `deliverable/_pipeline.py`.

### 2c. Hydro-correction strategy parameter

**Problem:** `breach_then_fill` can over-carve through legitimate closed depressions
(endorheic features, karst, wetlands, urban fill). A single fixed strategy will
produce wrong flow paths somewhere across arbitrary parcels.

**Fix:** Expose `strategy` as a parameter. Options: `breach_then_fill` (default),
`fill_only`, `breach_only`. Consider `BreachDepressionsLeastCost` with max breach
length as a middle ground. Log the number of breached cells so a human can
sanity-check.

**Files:** `deliverable/preprocess.py`, `deliverable/_pipeline.py`.

---

## Phase 3 — Replace agreement check with monotonicity-along-flow-path

**Problem:** The D8/D∞ accumulation distribution comparison with 0.50 tolerance is
too loose to catch real bugs (encoding-table corruption, masking off-by-ones,
nodata leakage). It's vestigial debugging scaffolding.

**Replacement:** Sample N random stream cells. For each, walk M steps downstream
following the flow pointer. Assert accumulation is non-decreasing along the walk.
For D∞, allow a small tolerance (flow-splitting means a cell's accumulation can be
slightly less than the sum of its upstream contributors under Tarboton partitioning).

**Remove:** `check_d8_dinf_agreement` call from `build_d8_1m()`.
**Add:** `verify_monotonicity_along_paths(accum, pointer, pointer_type)` called
after masking, before stream extraction.

**Files:** `deliverable/verify.py`, `deliverable/_pipeline.py`.

---

## Phase 4 — Structural cleanups (deferred)

### 4a. Strategy pattern for build functions

Four `build_*` functions following identical sequence. Replace with a single
`build(resolution, algorithm)` with algorithm-specific dispatch via small
functions or config object. Every new resolution or algorithm doubles the
function count with the current pattern.

### 4b. Resolution-aware renderer cell sizing

Replace `zoomBump = 3 for 10m, 0 for 1m` with cell footprint computed from
dataset resolution metadata: `cellSize = dataset_resolution_m / map_m_per_pixel`.
Eliminates per-dataset magic constants and works for any resolution.

### 4c. Binary format versioning

Add 4-byte magic + 1-byte version before the uint32 header. Costs 5 bytes,
prevents silent corruption from format changes.

### 4d. Point-in-polygon export validation

Replace bbox-of-boundary sanity check with proper point-in-polygon on top-K cells.
Bbox check passes for cells inside bbox but outside irregular polygon boundaries.

---

## Implementation order

```
Phase 1 (correctness)     → D∞ memo test + fix
Phase 2 (genericity)      → threshold, buffer, hydro strategy params  
Phase 3 (verification)    → monotonicity-along-path, remove agreement check
Phase 4 (structural)      → deferred, lowest priority
```

Phases 1-3 are independent of each other and can be done in any order after Phase 1.
Phase 1 first because it's a correctness bug that could silently produce wrong
results on arbitrary parcels.
