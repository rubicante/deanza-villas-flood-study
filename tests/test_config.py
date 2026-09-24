"""Layout / BuildParams, and the build cache that keys on them."""

import pytest

import floodflow.pipeline as pipeline
from floodflow.config import BuildParams, Layout
from floodflow.publish import record_dataset


def test_layouts_are_per_parcel(tmp_path):
    a = Layout.for_parcel("country_club", root=tmp_path)
    b = Layout.for_parcel("deanza_villas", root=tmp_path)
    for attr in ("run_dir", "rasters", "contributing_area", "publish_dir", "boundary"):
        assert getattr(a, attr) != getattr(b, attr), attr
    assert a.manifest == b.manifest  # one manifest for all parcels


def test_build_params_names_and_validation():
    p = BuildParams(10.0, "dinf")
    assert (p.dataset_key, p.binary_name) == ("dinf10m", "dinf_10m.bin")
    assert BuildParams(1.0, "dinf", reachability_mode="flow_weighted").binary_name == "dinf_1m_frac.bin"
    assert BuildParams(1.0, "d8").reachability_mode == "none"  # library default == CLI default
    with pytest.raises(ValueError):
        BuildParams(5.0, "dinf")
    with pytest.raises(ValueError):
        BuildParams(10.0, "mfd")


class _Stop(Exception):
    pass


@pytest.fixture
def no_fetch(monkeypatch):
    """Make any real work raise _Stop, so a test can tell 'cached' from 'rebuilt'."""
    def stop(*a, **k):
        raise _Stop
    monkeypatch.setattr(pipeline, "fetch_dem_10m", stop)
    monkeypatch.setattr(pipeline, "fetch_dem_1m", stop)


def _publish(layout, params):
    binary = layout.publish_dir / params.binary_name
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"x")
    record_dataset(layout, params, binary, {"cells": 1, "units": "area_m2", "resolution_m": 10.0})


def test_build_skips_when_params_match(tmp_path, no_fetch):
    layout = Layout.for_parcel("country_club", root=tmp_path)
    params = BuildParams(10.0, "dinf")
    _publish(layout, params)
    pipeline.build(layout, params)  # would raise _Stop if it rebuilt


@pytest.mark.parametrize("changed", [
    {"stream_threshold": 500},
    {"hydro_strategy": "fill_only"},
    {"threshold_frac": 0.001},
])
def test_build_reruns_when_params_change(tmp_path, no_fetch, changed):
    layout = Layout.for_parcel("country_club", root=tmp_path)
    _publish(layout, BuildParams(10.0, "dinf"))
    with pytest.raises(_Stop):
        pipeline.build(layout, BuildParams(10.0, "dinf", **changed))


def test_build_reruns_for_other_parcel(tmp_path, no_fetch):
    _publish(Layout.for_parcel("country_club", root=tmp_path), BuildParams(10.0, "dinf"))
    with pytest.raises(_Stop):
        pipeline.build(Layout.for_parcel("deanza_villas", root=tmp_path), BuildParams(10.0, "dinf"))
