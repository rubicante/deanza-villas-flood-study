"""Test D∞ flow-weighted reachability — three constructed grids.

Run: .venv/bin/python tests/test_dinf_reachability_weighted.py

Tests the _dinf_reachable_weighted function in isolation (no file I/O).
Hand-verifiable fraction values for each case.
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
sys.path.insert(0, str(ROOT))


# -- We'll import _dinf_reachable_weighted after it exists.
#    For now, import what we can and skip if not yet implemented.
try:
    from deliverable.reachability import _dinf_reachable_weighted
except ImportError:
    _dinf_reachable_weighted = None


def make_ptr(rows, cols, flows):
    ptr = np.zeros((rows, cols), dtype=np.float32)
    for (r, c), angle in flows.items():
        ptr[r, c] = angle
    return ptr


def make_streams(rows, cols, cells):
    s = np.zeros((rows, cols), dtype=np.uint8)
    for r, c in cells:
        s[r, c] = 1
    return s


def make_target(rows, cols, cells):
    t = np.zeros((rows, cols), dtype=np.uint8)
    for r, c in cells:
        t[r, c] = 1
    return t


def run_weighted(ptr, streams, target_mask):
    """Run _dinf_reachable_weighted and return (fractions, visited)."""
    fractions, n_cycle = _dinf_reachable_weighted(streams, ptr, target_mask)
    # Build visited mask: cells with fraction >= 0 are visited
    visited = (fractions >= 0).astype(np.uint8)
    return fractions, visited


# ═══════════════════════════════════════════════════════════
# Case 1: Simple split
#   A(0,0) at 292.5° splits 50/50 to S(270°) and SE(315°)
#   S  = (1,0) path → target(2,0)
#   SE = (1,1) path → pit(2,1)
#   A fraction = 0.5 (half the flow reaches)
# ═══════════════════════════════════════════════════════════

def test_case1_simple_split():
    ptr = make_ptr(3, 2, {
        (0, 0): 292.5,  # A splits 50/50 to S and SE
        (1, 0): 270.0,  # S neighbor → target (south)
        (1, 1): 270.0,  # SE neighbor → pit (south, off-target)
    })
    streams = make_streams(3, 2, [(0, 0), (1, 0), (1, 1)])
    target = make_target(3, 2, [(2, 0)])  # only (2,0) is target

    fractions, visited = run_weighted(ptr, streams, target)

    # A: 50% to S→target, 50% to SE→pit → 0.5
    assert abs(fractions[0, 0] - 0.5) < 0.001, (
        f"A fraction should be 0.5, got {fractions[0,0]}")
    # S neighbor: flows to target → 1.0
    assert abs(fractions[1, 0] - 1.0) < 0.001, (
        f"S fraction should be 1.0, got {fractions[1,0]}")
    # SE neighbor: flows to pit → 0.0
    assert abs(fractions[1, 1] - 0.0) < 0.001, (
        f"SE fraction should be 0.0, got {fractions[1,1]}")
    # Target: 1.0
    assert abs(fractions[2, 0] - 1.0) < 0.001

    print("  Case 1 PASS: simple split — A=0.5, S=1.0, SE=0.0")


# ═══════════════════════════════════════════════════════════
# Case 2: Split-then-rejoin
#   A(0,0) at 292.5° splits 50/50 to S(1,0) and SE(1,1)
#   S  → D(2,0) (south, single path)
#   SE → D(2,0) (southwest, single path)  — both reconverge at D
#   D  → target(3,0)
#
#   D = 1.0 (reaches target).
#   S = 1.0 × D = 1.0, SE = 1.0 × D = 1.0
#   A = 0.5×S + 0.5×SE = 0.5×1.0 + 0.5×1.0 = 1.0
#   Double-counting would give 2.0; single-branch would give 0.5.
# ═══════════════════════════════════════════════════════════

def test_case2_split_rejoin():
    ptr = make_ptr(4, 2, {
        (0, 0): 292.5,  # A splits to S(1,0) and SE(1,1)
        (1, 0): 270.0,  # S → D (south)
        (1, 1): 225.0,  # SE → D (southwest, exactly 225°)
        (2, 0): 270.0,  # D → target (south)
    })
    streams = make_streams(4, 2, [(0, 0), (1, 0), (1, 1), (2, 0)])
    target = make_target(4, 2, [(3, 0)])

    fractions, visited = run_weighted(ptr, streams, target)

    # D: flows directly to target → 1.0
    assert abs(fractions[2, 0] - 1.0) < 0.001, (
        f"D should be 1.0, got {fractions[2,0]}")

    # A: 0.5 * D_fraction + 0.5 * D_fraction = 1.0
    assert 0.9 < fractions[0, 0] < 1.1, (
        f"A should be ~1.0 (rejoin), got {fractions[0,0]}")

    # Not 2.0 (double-counting)
    assert fractions[0, 0] < 1.5, (
        f"A should not be >1.5 (possible double-counting), got {fractions[0,0]}")

    print(f"  Case 2 PASS: split-then-rejoin — A≈{fractions[0,0]:.3f}, D=1.0")


# ═══════════════════════════════════════════════════════════
# Case 3: Cycle + alternate path (parallels boolean case 2)
#   A(0,0) → B(1,0), C(1,1)  (D∞ split at 292.5°)
#   B → D → B (cycle on B↔D)
#   C → target(2,1)
#
#   A fraction: 0.5 * B_frac + 0.5 * C_frac
#   C: reaches target → 1.0
#   B/D: cycle → both branches contribute 0 from cycle branch → 0.0
#   A: 0.5 * 0.0 + 0.5 * 1.0 = 0.5
# ═══════════════════════════════════════════════════════════

def test_case3_cycle_alternate():
    ptr = make_ptr(3, 2, {
        (0, 0): 292.5,  # A splits to S(B) and SE(C)
        (1, 0): 270.0,  # B → D (south)
        (2, 0): 90.0,   # D → B (north) — back-edge, cycle!
        (1, 1): 270.0,  # C → target (south)
    })
    streams = make_streams(3, 2, [(0, 0), (1, 0), (1, 1), (2, 0)])
    target = make_target(3, 2, [(2, 1)])

    fractions, visited = run_weighted(ptr, streams, target)

    # C: reaches target → 1.0
    assert abs(fractions[1, 1] - 1.0) < 0.001, (
        f"C should be 1.0, got {fractions[1,1]}")
    # Target: 1.0
    assert abs(fractions[2, 1] - 1.0) < 0.001

    # B and D: cycle → both contribute 0 from cycle branch → 0.0
    assert fractions[1, 0] < 0.001, (
        f"B should be ~0.0 (cycle), got {fractions[1,0]}")
    assert fractions[2, 0] < 0.001, (
        f"D should be ~0.0 (cycle), got {fractions[2,0]}")

    # A: 0.5*0 + 0.5*1.0 = 0.5
    assert abs(fractions[0, 0] - 0.5) < 0.001, (
        f"A should be 0.5, got {fractions[0,0]}")

    # B and D should be VISITED (not unvisited) — they resolved as 0.0
    assert visited[1, 0] == 1, "B should be visited"
    assert visited[2, 0] == 1, "D should be visited"

    print("  Case 3 PASS: cycle + alternate — A=0.5, C=1.0, B/D≈0")


# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    if _dinf_reachable_weighted is None:
        print("SKIP: _dinf_reachable_weighted not yet implemented")
        sys.exit(0)

    failures = 0
    for name, fn in [
        ("Case 1: simple split", test_case1_simple_split),
        ("Case 2: split-then-rejoin", test_case2_split_rejoin),
        ("Case 3: cycle + alternate", test_case3_cycle_alternate),
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
