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
