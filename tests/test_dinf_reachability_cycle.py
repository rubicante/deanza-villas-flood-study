"""Test D∞ reachability cycle handling — three cases from project plan Phase 1.

Run: .venv/bin/python tests/test_dinf_reachability_cycle.py
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from deliverable.reachability import _dinf_trace, _dinf_reachable


def make_ptr(rows: int, cols: int, flows: dict[tuple[int, int], float]) -> np.ndarray:
    """Create a D∞ pointer array with specified flows. Unspecified cells get 0."""
    ptr = np.zeros((rows, cols), dtype=np.float32)
    for (r, c), angle in flows.items():
        ptr[r, c] = angle
    return ptr


def make_streams(rows: int, cols: int, cells: list[tuple[int, int]]) -> np.ndarray:
    s = np.zeros((rows, cols), dtype=np.uint8)
    for r, c in cells:
        s[r, c] = 1
    return s


def make_target(rows: int, cols: int, cells: list[tuple[int, int]]) -> np.ndarray:
    t = np.zeros((rows, cols), dtype=np.uint8)
    for r, c in cells:
        t[r, c] = 1
    return t


def trace_all(ptr, streams, target_mask):
    """Run _dinf_trace on all stream cells, return (results, cache, traced, hits)."""
    rows, cols = ptr.shape
    cache = np.zeros((rows, cols), dtype=np.uint8)
    results = {}
    total_traced = 0
    total_hits = 0
    stream_cells = np.argwhere(streams > 0)
    for r, c in stream_cells:
        reached, traced, hits = _dinf_trace(
            int(r), int(c), ptr, target_mask, cache, rows, cols)
        results[(int(r), int(c))] = reached
        total_traced += traced
        total_hits += hits
    return results, cache, total_traced, total_hits


# ═══════════════════════════════════════════════════════════════════
# Case 1: Cycle with no exit
#   A(0,0) → B(1,0) → C(2,0) → B  (cycle B↔C)
#   No target. All False, all cacheable.
# ═══════════════════════════════════════════════════════════════════

def test_case1_cycle_no_exit():
    # D∞ angles: 270° = S, 90° = N
    ptr = make_ptr(3, 1, {
        (0, 0): 270.0,  # A → B (S)
        (1, 0): 270.0,  # B → C (S)
        (2, 0): 90.0,   # C → B (N) — back-edge
    })
    streams = make_streams(3, 1, [(0, 0), (1, 0), (2, 0)])
    target = make_target(3, 1, [])  # no target

    results, cache, traced, hits = trace_all(ptr, streams, target)

    assert results[(0, 0)] == False, f"A should be False, got {results[(0,0)]}"
    assert results[(1, 0)] == False, f"B should be False, got {results[(1,0)]}"
    assert results[(2, 0)] == False, f"C should be False, got {results[(2,0)]}"

    # All three are safe to cache — cycle IS the whole story.
    # A (upstream) MUST be cached; B and C (in cycle) may or may not
    # be cached depending on implementation. Both are correct.
    assert cache[0, 0] == 2, f"A should be cached as 2, got {cache[0,0]}"
    # B and C: verify they're False (not poisoned as True), caching is optional
    assert cache[1, 0] != 1, f"B should not be cached as 1, got {cache[1,0]}"
    assert cache[2, 0] != 1, f"C should not be cached as 1, got {cache[2,0]}"

    print("  Case 1 PASS: cycle with no exit — all False, all cached")


# ═══════════════════════════════════════════════════════════════════
# Case 2: Cycle plus alternate path
#   A(0,0) → B(1,0), C(1,1)  (D∞ split: angle 292.5°)
#   B(1,0) → D(2,0)
#   D(2,0) → B(1,0)  (cycle B↔D)
#   C(1,1) → T(2,1)  (target)
#   T(2,1) = target
#   Expected: A=True, B=False, C=True, D=False
#   Cache: A=1, C=1.  B and D should NOT be in main cache.
# ═══════════════════════════════════════════════════════════════════

def test_case2_cycle_plus_alternate():
    ptr = make_ptr(3, 2, {
        (0, 0): 292.5,  # A splits to B(S, 270°) and C(SE, 315°)
        (1, 0): 270.0,  # B → D (S)
        (2, 0): 90.0,   # D → B (N) — back-edge
        (1, 1): 270.0,  # C → T (S)
    })
    streams = make_streams(3, 2, [(0, 0), (1, 0), (1, 1), (2, 0)])
    target = make_target(3, 2, [(2, 1)])

    results, cache, traced, hits = trace_all(ptr, streams, target)

    assert results[(0, 0)] == True, f"A should be True, got {results[(0,0)]}"
    assert results[(1, 0)] == False, f"B should be False, got {results[(1,0)]}"
    assert results[(1, 1)] == True, f"C should be True, got {results[(1,1)]}"
    assert results[(2, 0)] == False, f"D should be False, got {results[(2,0)]}"

    # A and C should be cached (clean results)
    assert cache[0, 0] == 1, f"A should be cached as 1, got {cache[0,0]}"
    assert cache[1, 1] == 1, f"C should be cached as 1, got {cache[1,1]}"

    # B and D should NOT be cached (cycle-determined)
    assert cache[1, 0] == 0, (
        f"B should NOT be cached (cycle-determined), got {cache[1,0]}")
    assert cache[2, 0] == 0, (
        f"D should NOT be cached (cycle-determined), got {cache[2,0]}")

    # T should be cached
    assert cache[2, 1] == 1, f"T should be cached as 1, got {cache[2,1]}"

    print("  Case 2 PASS: cycle + alternate path — B/D not cached, A/C cached")


# ═══════════════════════════════════════════════════════════════════
# Case 3: Cell upstream of a cycle, no other exit
#   A(0,0) → B(1,0) → C(2,0) → D(3,0) → C  (cycle C↔D)
#   No target.
#   Expected: A=False, B=False, C=False, D=False
#   C and D's False is cycle-determined — should NOT be cached.
#   A and B's False is clean (only path enters cycle) — SHOULD be cached.
# ═══════════════════════════════════════════════════════════════════

def test_case3_upstream_of_cycle():
    ptr = make_ptr(4, 1, {
        (0, 0): 270.0,  # A → B (S)
        (1, 0): 270.0,  # B → C (S)
        (2, 0): 270.0,  # C → D (S)
        (3, 0): 90.0,   # D → C (N) — back-edge
    })
    streams = make_streams(4, 1, [(0, 0), (1, 0), (2, 0), (3, 0)])
    target = make_target(4, 1, [])  # no target

    results, cache, traced, hits = trace_all(ptr, streams, target)

    assert results[(0, 0)] == False, f"A should be False, got {results[(0,0)]}"
    assert results[(1, 0)] == False, f"B should be False, got {results[(1,0)]}"
    assert results[(2, 0)] == False, f"C should be False, got {results[(2,0)]}"
    assert results[(3, 0)] == False, f"D should be False, got {results[(3,0)]}"

    # A and B should be cached (clean False — only path is into the cycle)
    assert cache[0, 0] == 2, f"A should be cached as 2, got {cache[0,0]}"
    assert cache[1, 0] == 2, f"B should be cached as 2, got {cache[1,0]}"

    # C and D should NOT be cached (cycle-determined)
    assert cache[2, 0] == 0, (
        f"C should NOT be cached (cycle-determined), got {cache[2,0]}")
    assert cache[3, 0] == 0, (
        f"D should NOT be cached (cycle-determined), got {cache[3,0]}")

    print("  Case 3 PASS: upstream of cycle — C/D not cached, A/B cached")


# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    failures = 0
    for name, fn in [
        ("Case 1: cycle, no exit", test_case1_cycle_no_exit),
        ("Case 2: cycle + alternate path", test_case2_cycle_plus_alternate),
        ("Case 3: upstream of cycle", test_case3_upstream_of_cycle),
    ]:
        try:
            fn()
        except AssertionError as e:
            print(f"  {name} FAIL: {e}")
            failures += 1

    if failures:
        print(f"\n{failures} test(s) FAILED")
        sys.exit(1)
    else:
        print("\nAll 3 tests PASSED")
