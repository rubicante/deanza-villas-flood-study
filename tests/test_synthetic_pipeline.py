"""End-to-end on a tiny synthetic DEM through real WhiteboxTools + pyflwdir.

A tilted V-valley: every cell drains laterally into the centre column, then
south to one outlet. Catches WBT / pyflwdir upgrades that change encoding or
accumulation units (see the version pins in pyproject.toml).
"""

import numpy as np
import pytest
import rasterio

from floodflow import (
    compute_d8_accum,
    compute_d8_pointer,
    compute_dinf,
    extract_streams,
    preprocess_dem,
    verify_accumulation,
    verify_monotonicity_along_paths,
)
from tests.helpers import write_raster

pytestmark = pytest.mark.wbt

N, CENTRE, RES = 41, 20, 10.0


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("synthetic")
    r, c = np.mgrid[0:N, 0:N]
    dem = (1000.0 + (N - r) * 0.5 * RES * 0.1 + np.abs(c - CENTRE) * 2.0 * RES * 0.1)
    dem_path = write_raster(tmp / "dem.tif", dem.astype("float32"), RES, nodata=-32768.0)
    filled = preprocess_dem(dem_path, output=tmp / "filled.tif")
    out = {"tmp": tmp, "filled": filled}
    out["dinf"] = compute_dinf(filled, output=tmp / "dinf.tif", pointer=tmp / "dinf_ptr.tif")
    out["d8_ptr"] = compute_d8_pointer(filled, output=tmp / "d8_ptr.tif")
    out["d8"] = compute_d8_accum(filled, output=tmp / "d8.tif", pointer=out["d8_ptr"])
    return out


def _read(path):
    with rasterio.open(path) as src:
        return src.read(1)


def test_d8_outlet_collects_whole_grid(run):
    acc = _read(run["d8"])
    r, c = np.unravel_index(np.argmax(acc), acc.shape)
    assert (r, c) == (N - 1, CENTRE)
    assert acc.max() >= 0.95 * N * N


def test_dinf_agrees_with_d8_at_outlet(run):
    d8, dinf = _read(run["d8"]), _read(run["dinf"])
    assert np.unravel_index(np.argmax(dinf), dinf.shape) == (N - 1, CENTRE)
    assert dinf.max() == pytest.approx(d8.max(), rel=0.05)


def test_verifiers_pass(run):
    for accum in (run["d8"], run["dinf"]):
        stats = verify_accumulation(accum)
        assert stats["nonzero_min"] == 1.0  # cell counts, not SCA
    assert verify_monotonicity_along_paths(run["d8"], run["d8_ptr"], "d8")["violations"] == 0
    assert verify_monotonicity_along_paths(
        run["dinf"], run["tmp"] / "dinf_ptr.tif", "dinf")["violations"] == 0


def test_streams_follow_the_valley(run):
    streams = _read(extract_streams(run["d8"], threshold=100, output=run["tmp"] / "s.tif"))
    rows, cols = np.nonzero(streams)
    assert len(rows) > 0
    assert np.mean(cols == CENTRE) > 0.9
