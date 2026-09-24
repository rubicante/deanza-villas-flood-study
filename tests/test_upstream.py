"""Contributing-area trace: defines the domain every dataset is built on."""

import geopandas as gpd
import numpy as np
import pytest

from floodflow.upstream import _neighbors_flowing_into, contributing_area
from tests.helpers import box_5070, write_raster


def test_neighbors_flowing_into_center():
    ptr = np.full((3, 3), -1.0, dtype="float32")
    ptr[0, 1] = 180.0   # N neighbour points S → into centre
    ptr[0, 2] = 225.0   # NE neighbour points SW → into centre
    ptr[1, 0] = 100.0   # W neighbour: E (90) + SE (135) split → E part enters centre
    ptr[2, 1] = 360.0   # S neighbour points N (360 == 0) → into centre
    ptr[1, 2] = 0.0     # E neighbour points N → misses centre
    ptr[2, 2] = 44.0    # SE neighbour: N + NE split → N part (-1, 0) lands on (1, 2), misses
    got = sorted(_neighbors_flowing_into(1, 1, ptr, 3, 3))
    assert got == [(0, 1), (0, 2), (1, 0), (2, 1)]


def test_neighbors_flowing_into_ignores_flats():
    ptr = np.full((3, 3), -1.0, dtype="float32")
    assert _neighbors_flowing_into(1, 1, ptr, 3, 3) == []


def _ptr_grid():
    """30×30 grid: a 5-column strip (cols 12–16, rows 5–24) flowing S into a
    target at rows 22–24; everything else is flat (-1)."""
    ptr = np.full((30, 30), -1.0, dtype="float32")
    ptr[5:25, 12:17] = 180.0
    ptr[25, 14] = 360.0   # below the target, pointing N into it
    return ptr


def test_contributing_area_traces_strip(tmp_path):
    pointer = write_raster(tmp_path / "ptr.tif", _ptr_grid())
    target = gpd.GeoDataFrame(geometry=[box_5070(22, 12, 25, 17)], crs="EPSG:5070")
    gdf = contributing_area(pointer, target, output_mask=tmp_path / "mask.tif")
    # strip rows 5–24 × 5 cols = 100 cells, plus the 360° cell below
    assert gdf.iloc[0]["cells"] == 101
    assert gdf.iloc[0]["area_km2"] == pytest.approx(101 * 100 / 1e6, abs=0.01)
    assert gdf.crs.to_epsg() == 4326


def test_contributing_area_raises_at_dem_edge(tmp_path):
    ptr = _ptr_grid()
    ptr[0:5, 12:17] = 180.0   # strip now reaches the top edge
    pointer = write_raster(tmp_path / "ptr.tif", ptr)
    target = gpd.GeoDataFrame(geometry=[box_5070(22, 12, 25, 17)], crs="EPSG:5070")
    with pytest.raises(RuntimeError, match="reached the pointer boundary"):
        contributing_area(pointer, target)


def _reference_trace(ptr, target):
    """Plain-Python BFS over _neighbors_flowing_into (the readable spec)."""
    from collections import deque
    rows, cols = ptr.shape
    visited = target.astype("uint8").copy()
    queue = deque(zip(*np.nonzero(target)))
    while queue:
        r, c = queue.popleft()
        for nr, nc in _neighbors_flowing_into(int(r), int(c), ptr, rows, cols):
            if not visited[nr, nc]:
                visited[nr, nc] = 1
                queue.append((nr, nc))
    return visited


@pytest.mark.parametrize("seed", range(20))
def test_numba_trace_matches_reference(seed):
    from floodflow.upstream import _trace_upstream
    rng = np.random.default_rng(seed)
    shape = (int(rng.integers(5, 60)), int(rng.integers(5, 60)))
    ptr = rng.uniform(0, 360, shape).astype("float32")
    # sprinkle the edge cases: flats, exact multiples of 45°, 360°
    special = rng.random(shape)
    ptr[special < 0.10] = -1.0
    ptr[(special >= 0.10) & (special < 0.20)] = rng.integers(0, 8, shape)[(special >= 0.10) & (special < 0.20)] * 45.0
    ptr[(special >= 0.20) & (special < 0.23)] = 360.0
    target = np.zeros(shape, dtype="uint8")
    target[rng.integers(0, shape[0]), rng.integers(0, shape[1])] = 1
    target[rng.integers(0, shape[0]), rng.integers(0, shape[1])] = 1
    assert np.array_equal(_trace_upstream(ptr, target), _reference_trace(ptr, target))


def test_numba_trace_ignores_nan():
    from floodflow.upstream import _trace_upstream
    ptr = np.full((3, 3), np.nan, dtype="float32")
    ptr[0, 1] = 180.0
    target = np.zeros((3, 3), dtype="uint8")
    target[1, 1] = 1
    assert _trace_upstream(ptr, target).sum() == 2
