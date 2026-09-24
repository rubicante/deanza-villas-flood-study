"""Everything the explorer (docs/index.html) reads: the stream binary format
and docs/data/manifest.json.

Manifest layout (paths are relative to docs/data/):

    {
      "format_version": 2,
      "default_parcel": "country_club",
      "layers": {"huc12": "...geojson", "fema": "...geojson"},   # hand-maintained
      "parcels": {
        "<key>": {
          "name": "...",
          "boundary": "<key>/parcel_boundary.geojson",
          "contributing_area": "<key>/parcel_contributing_area.geojson",
          "contributing_area_dem": {...} | null,
          "datasets": {
            "dinf10m": {"file": "<key>/dinf_10m.bin", "algorithm": "dinf",
                        "resolution_m": 10.0, "units": "area_m2",
                        "cells": 27887, "params": {...} | null,
                        "built_utc": "...", "dem": {...} | null}
          }
        }
      }
    }

`dem` / `contributing_area_dem` record the TNM tiles (title, publication
date) the DEM was mosaicked from — see fetch.provenance_path. Rebuilds do
not re-check TNM for newer tiles; `floodflow clean` forces that.

`params` is the BuildParams dict the dataset was built with. The pipeline
skips a build only when the recorded params match; null (unknown) never
matches.
"""

from __future__ import annotations

import json
import shutil
import struct
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.warp import transform as rio_transform

from floodflow.config import DEFAULT_PARCEL, TARGET_CRS, BuildParams, Layout
from floodflow.fetch import read_provenance

# -- Binary format v2 (little-endian) --
#   0  uint32   magic 0x48465342 ("HFSB")
#   4  uint32   version = 2
#   8  uint32   n_cells
#  12  float32  cell resolution (m)
#  16  uint32   value units: 0 = drainage area (m²), 1 = flow fraction (0–1)
#  20  uint32   reserved (0)
#  24  float64  origin lon
#  32  float64  origin lat
#  40  float32  n_cells × [value, lon - origin_lon, lat - origin_lat],
#               sorted by value descending
# Offsets from a float64 origin keep ~1 mm precision; absolute float32
# lon/lat (v1) quantized to ~0.7 m, visible at 1m resolution.
BINARY_MAGIC = 0x48465342
BINARY_VERSION = 2
UNITS_AREA_M2 = 0
UNITS_FRACTION = 1
_UNIT_NAMES = {UNITS_AREA_M2: "area_m2", UNITS_FRACTION: "fraction"}
HEADER = struct.Struct("<IIIfII dd")


def export_binary(
    streams: Path,
    accum: Path,
    output: Path,
    source_crs: str = TARGET_CRS,
    target_crs: str = "EPSG:4326",
    boundary: Path | None = None,
    fraction_raster: Path | None = None,
) -> dict:
    """Export sorted binary for the explorer (format v2, see above).

    Accumulation (cell counts) is converted to drainage area in m² so
    datasets at different resolutions share one threshold scale.
    If fraction_raster is provided, its values replace accumulation as the
    sort key (for flow-weighted reachability where values are 0.0–1.0
    fractions rather than raw accumulation counts).

    Returns {"cells", "units", "resolution_m"} for the manifest."""
    output.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(streams) as src:
        sdata = src.read(1)
        transform_s = src.transform
    with rasterio.open(accum) as src_acc:
        accum_data = src_acc.read(1)
    res_x, res_y = abs(transform_s.a), abs(transform_s.e)

    rows, cols = np.where(sdata > 0)
    n_cells = len(rows)

    xs = transform_s.c + (cols + 0.5) * transform_s.a
    ys = transform_s.f + (rows + 0.5) * transform_s.e
    lons, lats = rio_transform(source_crs, target_crs, xs, ys)
    lons = np.asarray(lons, dtype="float64")
    lats = np.asarray(lats, dtype="float64")

    # Use fraction raster as sort key if provided
    if fraction_raster is not None:
        with rasterio.open(fraction_raster) as src_frac:
            frac_data = src_frac.read(1)
        sort_values = frac_data[rows, cols].astype("float64")
        units = UNITS_FRACTION
    else:
        sort_values = accum_data[rows, cols].astype("float64") * res_x * res_y
        units = UNITS_AREA_M2

    order = np.argsort(sort_values)[::-1]
    sort_values = sort_values[order]
    lons = lons[order]
    lats = lats[order]

    assert np.sum(np.isinf(sort_values)) == 0, "inf in export"
    assert np.sum(np.isnan(sort_values)) == 0, "nan in export"

    origin_lon = float(lons.min()) if n_cells else 0.0
    origin_lat = float(lats.min()) if n_cells else 0.0
    body = np.empty((n_cells, 3), dtype="<f4")
    body[:, 0] = sort_values
    body[:, 1] = lons - origin_lon
    body[:, 2] = lats - origin_lat
    with open(output, "wb") as f:
        f.write(HEADER.pack(BINARY_MAGIC, BINARY_VERSION, n_cells,
                            res_x, units, 0, origin_lon, origin_lat))
        body.tofile(f)

    # Sanity: top-10 cells within boundary polygon (buffered 10 m in the
    # projected CRS — outlet cells may sit right on the polygon edge).
    if boundary:
        ws = gpd.read_file(boundary)
        ws_geom = ws.to_crs(source_crs).geometry.iloc[0].buffer(10)
        k = min(10, n_cells)
        top = order[:k]
        pts = gpd.points_from_xy(xs[top], ys[top], crs=source_crs)
        for i, pt in enumerate(pts):
            if not ws_geom.contains(pt):
                raise AssertionError(
                    f"Cell {i} ({lons[i]:.6f}, {lats[i]:.6f}) "
                    f"outside buffered boundary polygon")

    print(f"  Binary: {n_cells:,} cells, {output.stat().st_size/1e6:.1f}MB → {output}")
    return {"cells": n_cells, "units": _UNIT_NAMES[units], "resolution_m": res_x}


# -- Manifest --

def read_manifest(layout: Layout) -> dict:
    if layout.manifest.exists():
        return json.loads(layout.manifest.read_text())
    return {"format_version": BINARY_VERSION, "default_parcel": DEFAULT_PARCEL,
            "layers": {}, "parcels": {}}


def write_manifest(layout: Layout, manifest: dict) -> None:
    layout.manifest.parent.mkdir(parents=True, exist_ok=True)
    layout.manifest.write_text(json.dumps(manifest, indent=2) + "\n")


def _rel(layout: Layout, path: Path) -> str:
    return path.relative_to(layout.publish_root).as_posix()


def _parcel_entry(manifest: dict, layout: Layout) -> dict:
    entry = manifest["parcels"].setdefault(layout.parcel.key, {})
    entry["name"] = layout.parcel.name
    entry.setdefault("datasets", {})
    return entry


def published_params(layout: Layout, params: BuildParams) -> dict | None:
    """Params recorded for this dataset, or None if it isn't published."""
    entry = read_manifest(layout)["parcels"].get(layout.parcel.key, {})
    ds = entry.get("datasets", {}).get(params.dataset_key)
    if ds is None or not (layout.publish_root / ds["file"]).exists():
        return None
    return ds.get("params")


def publish_parcel_layers(layout: Layout) -> None:
    """Copy the parcel boundary and contributing area into docs/data/<parcel>/
    and register them in the manifest."""
    layout.publish_dir.mkdir(parents=True, exist_ok=True)
    boundary = layout.publish_dir / "parcel_boundary.geojson"
    ca = layout.publish_dir / "parcel_contributing_area.geojson"
    shutil.copy(layout.boundary, boundary)
    shutil.copy(layout.contributing_area, ca)
    manifest = read_manifest(layout)
    entry = _parcel_entry(manifest, layout)
    entry["boundary"] = _rel(layout, boundary)
    entry["contributing_area"] = _rel(layout, ca)
    entry["contributing_area_dem"] = read_provenance(layout.contributing_area)
    write_manifest(layout, manifest)


def record_dataset(layout: Layout, params: BuildParams, binary: Path, info: dict) -> None:
    manifest = read_manifest(layout)
    entry = _parcel_entry(manifest, layout)
    entry["datasets"][params.dataset_key] = {
        "file": _rel(layout, binary),
        "algorithm": params.algorithm,
        "resolution_m": info["resolution_m"],
        "units": info["units"],
        "cells": info["cells"],
        "params": params.to_dict(),
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dem": info.get("dem"),
    }
    write_manifest(layout, manifest)


def unpublish_datasets(layout: Layout) -> None:
    """Delete every published binary (all parcels) and drop them from the
    manifest. Parcel layers and hand-maintained reference layers stay."""
    manifest = read_manifest(layout)
    for entry in manifest["parcels"].values():
        for ds in entry.get("datasets", {}).values():
            f = layout.publish_root / ds["file"]
            if f.exists():
                f.unlink()
                print(f"  removed {f}")
        entry["datasets"] = {}
    if layout.manifest.exists():
        write_manifest(layout, manifest)
