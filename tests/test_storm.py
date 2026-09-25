"""Atlas 14 parsing and the alternating-block hyetograph (no network)."""

import numpy as np
import pytest

from floodflow.storm import (
    ARI_YEARS,
    DURATIONS_MIN,
    MM_PER_IN,
    PFTable,
    alternating_block,
    parse_pfds,
)


def _table() -> PFTable:
    # Depth grows as duration^0.3 and with ARI: a plausible, strictly nested table
    d = np.array(DURATIONS_MIN, float)[:, None] ** 0.3
    return PFTable(33.0, -116.0, d * np.log1p(np.array(ARI_YEARS, float))[None, :] * 5, {})


def test_parse_pfds_response():
    rows = [[f"{0.1 * (i + 1) * (j + 1):.3f}" for j in range(10)] for i in range(19)]
    text = (f"result = 'values';\nquantiles = {rows!r};\nupper = [['9']];\n"
            "region = 'Southwest';\nvolume = '6';\nversion = '2';\nunit = 'english';\n")
    table, meta = parse_pfds(text)
    assert table.shape == (19, 10)
    assert table[4, 6] == pytest.approx(0.1 * 5 * 7)
    assert meta == {"region": "Southwest", "volume": "6", "version": "2", "unit": "english"}
    assert MM_PER_IN == 25.4


def test_interpolation_hits_table_values():
    t = _table()
    assert np.allclose(t.depth_mm_at(DURATIONS_MIN, 100), t.column(100))
    assert t.column(100)[4] < t.depth_mm_at(90, 100) < t.column(100)[5]


@pytest.mark.parametrize("peak_frac", [0.5, 0.25])
def test_alternating_block_is_nested(peak_frac):
    """Total = the duration's depth; every k-block window around the peak
    holds the k × 5-minute depth, so the storm is critical at all durations."""
    t = _table()
    blocks_mm = alternating_block(t, 100, 360, peak_frac=peak_frac) * 300 * 1e3
    assert blocks_mm.sum() == pytest.approx(t.depth_mm_at(360, 100))
    cum = t.depth_mm_at(5 * np.arange(1, 73), 100)
    for k in (1, 3, 12, 24, 72):
        best = np.convolve(blocks_mm, np.ones(k), "valid").max()
        assert best == pytest.approx(cum[k - 1])
    assert np.argmax(blocks_mm) == int(peak_frac * 72)
