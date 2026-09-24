"""Binary format v2 and the manifest the explorer reads."""

import numpy as np
import pytest
from rasterio.warp import transform as rio_transform

from floodflow.config import BuildParams, Layout
from floodflow.publish import (
    BINARY_MAGIC,
    BINARY_VERSION,
    HEADER,
    UNITS_AREA_M2,
    export_binary,
    published_params,
    read_manifest,
    record_dataset,
    unpublish_datasets,
)
from tests.helpers import X0, Y0, box_5070, write_geojson_4326, write_raster

RES = 10.0
CELLS = [(2, 3, 5.0), (10, 10, 400.0), (15, 4, 37.0)]  # (row, col, accum cells)


@pytest.fixture
def rasters(tmp_path):
    streams = np.zeros((20, 20), dtype="uint8")
    accum = np.zeros((20, 20), dtype="float32")
    for r, c, a in CELLS:
        streams[r, c] = 1
        accum[r, c] = a
    return (write_raster(tmp_path / "streams.tif", streams, RES),
            write_raster(tmp_path / "accum.tif", accum, RES))


def read_binary(path):
    buf = path.read_bytes()
    header = HEADER.unpack_from(buf, 0)
    body = np.frombuffer(buf, dtype="<f4", offset=HEADER.size).reshape(-1, 3)
    return header, body


def test_export_round_trip(tmp_path, rasters):
    inside = write_geojson_4326(tmp_path / "inside.geojson", box_5070(0, 0, 20, 20))
    info = export_binary(*rasters, tmp_path / "out.bin", boundary=inside)
    (magic, version, n, res, units, _, olon, olat), body = read_binary(tmp_path / "out.bin")
    assert (magic, version, n, res, units) == (BINARY_MAGIC, BINARY_VERSION, 3, RES, UNITS_AREA_M2)
    assert info == {"cells": 3, "units": "area_m2", "resolution_m": RES}
    # drainage area in m², sorted descending
    assert list(body[:, 0]) == [400.0 * RES**2, 37.0 * RES**2, 5.0 * RES**2]
    # coordinates reconstruct the cell centre to well under 1 cm
    lon, lat = rio_transform("EPSG:5070", "EPSG:4326",
                             [X0 + 10.5 * RES], [Y0 - 10.5 * RES])
    assert abs(olon + float(body[0, 1]) - lon[0]) * 93_000 < 0.01
    assert abs(olat + float(body[0, 2]) - lat[0]) * 111_000 < 0.01


def test_export_boundary_check_fires(tmp_path, rasters):
    # v1 buffered by 10 degrees here, so this could never fail
    far = write_geojson_4326(tmp_path / "far.geojson", box_5070(500, 500, 520, 520))
    with pytest.raises(AssertionError, match="outside buffered boundary"):
        export_binary(*rasters, tmp_path / "out.bin", boundary=far)


def test_manifest_records_and_matches_params(tmp_path):
    layout = Layout.for_parcel("deanza_villas", root=tmp_path)
    params = BuildParams(10.0, "dinf")
    binary = layout.publish_dir / params.binary_name
    assert published_params(layout, params) is None

    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"x")
    record_dataset(layout, params, binary, {"cells": 3, "units": "area_m2", "resolution_m": 10.0})
    ds = read_manifest(layout)["parcels"]["deanza_villas"]["datasets"]["dinf10m"]
    assert ds["file"] == "deanza_villas/dinf_10m.bin"
    assert published_params(layout, params) == params.to_dict()

    binary.unlink()  # a recorded dataset whose file is missing is not published
    assert published_params(layout, params) is None


def test_unpublish_keeps_layers(tmp_path):
    layout = Layout.for_parcel("country_club", root=tmp_path)
    params = BuildParams(1.0, "d8")
    binary = layout.publish_dir / params.binary_name
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"x")
    record_dataset(layout, params, binary, {"cells": 1, "units": "area_m2", "resolution_m": 1.0})
    manifest = read_manifest(layout)
    manifest["layers"] = {"fema": "nfhl.geojson"}
    layout.manifest.write_text(__import__("json").dumps(manifest))

    unpublish_datasets(layout)
    after = read_manifest(layout)
    assert not binary.exists()
    assert after["parcels"]["country_club"]["datasets"] == {}
    assert after["layers"] == {"fema": "nfhl.geojson"}


def test_manifest_carries_dem_provenance(tmp_path):
    layout = Layout.for_parcel("country_club", root=tmp_path)
    params = BuildParams(10.0, "d8")
    binary = layout.publish_dir / params.binary_name
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"x")
    dem = {"tiles": [{"title": "USGS 1/3 Arc Second n34w117 20260915",
                      "publicationDate": "2026-09-15"}]}
    record_dataset(layout, params, binary,
                   {"cells": 1, "units": "area_m2", "resolution_m": 10.0, "dem": dem})
    ds = read_manifest(layout)["parcels"]["country_club"]["datasets"]["d810m"]
    assert ds["dem"] == dem
