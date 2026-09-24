"""Direction tables: the one place an encoding error would corrupt everything."""

import pytest
from pyflwdir.core_d8 import _ds as PYFLWDIR_DS  # [dr+1, dc+1] → pyflwdir code

from floodflow.encoding import D8_DELTA, DINF_NEIGHBORS, WBT_TO_PYFLWDIR, dinf_neighbors


def test_wbt_to_pyflwdir_lut_matches_pyflwdir_table():
    for wbt_code, (dr, dc) in D8_DELTA.items():
        assert WBT_TO_PYFLWDIR[wbt_code] == PYFLWDIR_DS[dr + 1, dc + 1], wbt_code


def test_lut_maps_nodata_and_unknown_codes_to_zero():
    known = set(D8_DELTA)
    assert all(WBT_TO_PYFLWDIR[v] == 0 for v in range(256) if v not in known)


def test_d8_and_dinf_tables_agree():
    # D∞ index 0=N clockwise; WBT D8 codes 128=N, 1=NE, 2=E, ... clockwise
    d8_clockwise_from_n = [128, 1, 2, 4, 8, 16, 32, 64]
    assert [D8_DELTA[c] for c in d8_clockwise_from_n] == DINF_NEIGHBORS


@pytest.mark.parametrize("angle, expected", [
    (0.0, [(-1, 0, 1.0)]),       # N
    (45.0, [(-1, 1, 1.0)]),      # NE
    (90.0, [(0, 1, 1.0)]),       # E
    (180.0, [(1, 0, 1.0)]),      # S
    (360.0, [(-1, 0, 1.0)]),     # 360 wraps to N
    (22.5, [(-1, 0, 0.5), (-1, 1, 0.5)]),
    (200.0, [(1, 0, 25 / 45), (1, -1, 20 / 45)]),
])
def test_dinf_neighbors(angle, expected):
    got = dinf_neighbors(angle, with_proportions=True)
    assert [g[:2] for g in got] == [e[:2] for e in expected]
    assert [g[2] for g in got] == pytest.approx([e[2] for e in expected])


def test_dinf_neighbors_near_360_splits_nw_and_n():
    got = dinf_neighbors(359.0, with_proportions=True)
    assert [g[:2] for g in got] == [(-1, -1), (-1, 0)]
    assert sum(g[2] for g in got) == pytest.approx(1.0)


@pytest.mark.parametrize("angle", [-1.0, 361.0])
def test_dinf_neighbors_invalid(angle):
    assert dinf_neighbors(angle) == []
