"""
Project-specific: Henderson Canyon watershed — four artifacts for the
threshold morph explorer. Thin CLI over the deliverable library.

Owns the binary export format and CRS conversion that the explorer needs.
"""
from pathlib import Path
import struct, time, sys
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.warp import transform as rio_transform

from deliverable import (
    fetch_dem, preprocess_dem,
    compute_d8_pointer, compute_d8_accum,
    compute_dinf,
    extract_streams,
    verify_accumulation, check_d8_dinf_agreement,
)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "vectors"
MAPS = ROOT / "outputs" / "maps"
PROCESSED = ROOT / "data" / "processed" / "terrain"
DERIVED = ROOT / "data" / "derived" / "henderson"
TARGET_CRS = "EPSG:5070"

BOUNDARY = DATA / "henderson_watershed_boundary.geojson"

# Input DEMs (fetched, unfilled)
DEM_1M = PROCESSED / "dem_1m_5070.tif"
DEM_10M = PROCESSED / "dem_10m_wide.tif"


def _export_binary(
    streams: Path,
    accum: Path,
    output: Path,
    source_crs: str = TARGET_CRS,
    target_crs: str = "EPSG:4326",
    boundary: Path | None = None,
) -> Path:
    """
    Export sorted binary for the explorer: uint32 header + stride-3 float32
    [accum, lon, lat] sorted by accum descending.
    """
    output.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(streams) as src:
        sdata = src.read(1)
        transform_s = src.transform
        src_crs = src.crs
    with rasterio.open(accum) as src_acc:
        accum_data = src_acc.read(1)

    rows, cols = np.where(sdata > 0)
    n_cells = len(rows)

    xs = transform_s.c + (cols + 0.5) * transform_s.a
    ys = transform_s.f + (rows + 0.5) * transform_s.e
    lons, lats = rio_transform(source_crs, target_crs, xs, ys)
    lons = np.asarray(lons, dtype="float64")
    lats = np.asarray(lats, dtype="float64")

    accums = accum_data[rows, cols]
    order = np.argsort(accums)[::-1]
    accums = accums[order]
    lons = lons[order]
    lats = lats[order]

    assert np.sum(np.isinf(accums)) == 0, "inf in export"
    assert np.sum(np.isnan(accums)) == 0, "nan in export"

    with open(output, "wb") as f:
        f.write(struct.pack("I", n_cells))
        for i in range(n_cells):
            f.write(struct.pack("fff", float(accums[i]), float(lons[i]), float(lats[i])))

    # Sanity: first cell in boundary bbox
    if boundary:
        ws = gpd.read_file(boundary)
        ws_bounds = ws.to_crs(target_crs).total_bounds
        assert ws_bounds[0] <= lons[0] <= ws_bounds[2], "first lon outside boundary"
        assert ws_bounds[1] <= lats[0] <= ws_bounds[3], "first lat outside boundary"

    print(f"  Binary: {n_cells:,} cells, {output.stat().st_size/1e6:.1f}MB → {output}")
    return output


def build_dinf_1m():
    """D∞ 1m for 107 km² watershed."""
    DERIVED.mkdir(parents=True, exist_ok=True)
    dem = DERIVED / "dem_1m_filled_f32.tif"
    accum = DERIVED / "dinf_flow_accum_1m.tif"
    streams = DERIVED / "streams_dinf_1m_250.tif"

    if not dem.exists():
        raw = fetch_dem(BOUNDARY, resolution=1.0, crs=TARGET_CRS, buffer_m=200,
                        output=DERIVED / "dem_1m_clipped.tif")
        dem = preprocess_dem(raw, output=dem)

    compute_dinf(dem, output=accum)
    verify_accumulation(accum)
    extract_streams(accum, threshold=250, output=streams)
    _export_binary(streams, accum, MAPS / "streams_all.bin", boundary=BOUNDARY)


def build_dinf_10m():
    """D∞ 10m for 107 km² watershed, watershed-clipped."""
    DERIVED.mkdir(parents=True, exist_ok=True)
    dem = DERIVED / "dem_10m_filled.tif"
    accum = DERIVED / "dinf_flow_accum_10m.tif"
    accum_masked = DERIVED / "dinf_flow_accum_10m_masked.tif"
    streams = DERIVED / "streams_dinf_10m_250.tif"

    if not dem.exists():
        dem = preprocess_dem(DEM_10M, output=dem, strategy="breach_then_fill")

    compute_dinf(dem, output=accum)

    # Clip to watershed
    ws = gpd.read_file(BOUNDARY)
    with rasterio.open(accum) as src:
        da = src.read(1)
        prof = src.profile.copy()
    with rasterio.open(DERIVED / "watershed_wide.tif") as ws_rast:
        ws_mask = ws_rast.read(1) > 0
    masked = np.where(ws_mask, da, 0).astype(prof["dtype"])
    with rasterio.open(accum_masked, "w", **prof) as dst:
        dst.write(masked, 1)

    verify_accumulation(accum_masked)
    extract_streams(accum_masked, threshold=250, output=streams)
    _export_binary(streams, accum_masked, MAPS / "streams_wide_dinf.bin", boundary=BOUNDARY)


def build_d8_1m():
    """D8 1m for 107 km² watershed."""
    DERIVED.mkdir(parents=True, exist_ok=True)
    dem = DERIVED / "dem_1m_filled_f32.tif"
    ptr = DERIVED / "d8_pointer_1m.tif"
    accum = DERIVED / "d8_flow_accum_1m.tif"
    streams = DERIVED / "streams_d8_1m_250.tif"

    if not dem.exists():
        raw = fetch_dem(BOUNDARY, resolution=1.0, crs=TARGET_CRS, buffer_m=200,
                        output=DERIVED / "dem_1m_clipped.tif")
        dem = preprocess_dem(raw, output=dem)

    compute_d8_pointer(dem, output=ptr)
    compute_d8_accum(dem, output=accum, pointer=ptr, backend="wbt_ptr_pyflwdir")

    verify_accumulation(accum)
    # Cross-check against D∞
    dinf = DERIVED / "dinf_flow_accum_1m.tif"
    if dinf.exists():
        check_d8_dinf_agreement(accum, dinf, tolerance=0.07)

    extract_streams(accum, threshold=250, output=streams)
    _export_binary(streams, accum, MAPS / "streams_d8_1m.bin", boundary=BOUNDARY)


def build_d8_10m():
    """D8 10m for 107 km² watershed."""
    DERIVED.mkdir(parents=True, exist_ok=True)
    dem = DERIVED / "dem_10m_filled.tif"
    ptr = DERIVED / "d8_pointer_10m.tif"
    accum = DERIVED / "d8_flow_accum_10m.tif"
    streams = DERIVED / "streams_d8_10m_250.tif"

    if not dem.exists():
        dem = preprocess_dem(DEM_10M, output=dem, strategy="breach_then_fill")

    compute_d8_pointer(dem, output=ptr)
    compute_d8_accum(dem, output=accum, pointer=ptr, backend="wbt_ptr_pyflwdir")

    verify_accumulation(accum)

    # Mask to watershed
    ws = gpd.read_file(BOUNDARY)
    accum_masked = DERIVED / "d8_flow_accum_10m_masked.tif"
    with rasterio.open(accum) as src:
        da = src.read(1)
        prof = src.profile.copy()
    with rasterio.open(DERIVED / "watershed_wide.tif") as ws_rast:
        ws_mask = ws_rast.read(1) > 0
    masked = np.where(ws_mask, da, 0).astype(prof["dtype"])
    with rasterio.open(accum_masked, "w", **prof) as dst:
        dst.write(masked, 1)

    verify_accumulation(accum_masked)
    extract_streams(accum_masked, threshold=250, output=streams)
    _export_binary(streams, accum_masked, MAPS / "streams_wide_d8.bin", boundary=BOUNDARY)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python _henderson.py [dinf1m|dinf10m|d81m|d810m|all]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "dinf1m":
        build_dinf_1m()
    elif cmd == "dinf10m":
        build_dinf_10m()
    elif cmd == "d81m":
        build_d8_1m()
    elif cmd == "d810m":
        build_d8_10m()
    elif cmd == "all":
        build_dinf_1m()
        build_dinf_10m()
        build_d8_1m()
        build_d8_10m()
    else:
        print(f"Unknown: {cmd}")
        sys.exit(1)
