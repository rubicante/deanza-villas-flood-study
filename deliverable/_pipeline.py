"""
Project-specific: De Anza Villas parcel contributing area — four artifacts
for the threshold morph explorer. Thin CLI over the deliverable library.

Owns the binary export format and CRS conversion that the explorer needs.
"""

import argparse
import struct, time, sys
from pathlib import Path

import numpy as np
import geopandas as gpd
import rasterio
from rasterio.warp import transform as rio_transform

from deliverable import (
    fetch_dem, preprocess_dem,
    compute_d8_pointer, compute_d8_accum,
    compute_dinf,
    extract_streams,
    verify_accumulation, verify_monotonicity_along_paths,
)
from deliverable.reachability import filter_reachable

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "derived" / "vectors"
MAPS = ROOT / "outputs" / "maps"
DERIVED = ROOT / "data" / "derived" / "watershed"
TARGET_CRS = "EPSG:5070"

CONTRIBUTING_AREA = DATA / "deanza_parcel_contributing_area.geojson"
CONTRIBUTING_AREA_5070 = DATA / "deanza_parcel_contributing_area_5070.geojson"
PARCEL = ROOT / "data" / "raw" / "sangis" / "deanza_villas_complex_boundary.geojson"


# -- Binary output name mapping (hardcoded: explorer expects these names) --

_BINARY_NAMES: dict[tuple[float, str], str] = {
    (1.0, "dinf"): "streams_all.bin",
    (10.0, "dinf"): "streams_wide_dinf.bin",
    (1.0, "d8"): "streams_d8_1m.bin",
    (10.0, "d8"): "streams_wide_d8.bin",
}


# -- Helpers --

def _mask_to_boundary(raster_path: Path, boundary: Path,
                      output_path: Path) -> Path:
    """Mask a raster to a GeoJSON boundary polygon. Returns output Path."""
    gdf = gpd.read_file(boundary)
    gdf_proj = gdf.to_crs(TARGET_CRS)
    with rasterio.open(raster_path) as src:
        data = src.read(1)
        prof = src.profile.copy()
    mask = rasterio.features.rasterize(
        [(gdf_proj.geometry.iloc[0], 1)],
        out_shape=data.shape, transform=prof["transform"], dtype="uint8",
    )
    masked = np.where(mask, data, 0).astype(prof["dtype"])
    with rasterio.open(output_path, "w", **prof) as dst:
        dst.write(masked, 1)
    return output_path


def _export_binary(
    streams: Path,
    accum: Path,
    output: Path,
    source_crs: str = TARGET_CRS,
    target_crs: str = "EPSG:4326",
    boundary: Path | None = None,
) -> Path:
    """Export sorted binary for explorer: uint32 header + stride-3 float32."""
    output.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(streams) as src:
        sdata = src.read(1)
        transform_s = src.transform
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
        f.write(struct.pack("I", 0x48465342))  # magic: "HFSB"
        f.write(struct.pack("I", 1))            # version
        f.write(struct.pack("I", n_cells))
        for i in range(n_cells):
            f.write(struct.pack("fff", float(accums[i]), float(lons[i]),
                                float(lats[i])))
    # Sanity: top-10 cells within boundary polygon (buffered 10m — outlet
    # cells may sit right on the polygon edge).
    if boundary:
        ws = gpd.read_file(boundary)
        ws_geom = ws.to_crs(target_crs).geometry.iloc[0].buffer(10)
        k = min(10, n_cells)
        for i in range(k):
            pt = gpd.points_from_xy([lons[i]], [lats[i]], crs=target_crs)[0]
            if not ws_geom.contains(pt):
                raise AssertionError(
                    f"Cell {i} ({lons[i]:.6f}, {lats[i]:.6f}) "
                    f"outside buffered boundary polygon")

    print(f"  Binary: {n_cells:,} cells, {output.stat().st_size/1e6:.1f}MB → {output}")
    return output


# -- Build --

def build(
    resolution: float,
    algorithm: str,
    *,
    stream_threshold: int = 250,
    threshold_frac: float | None = None,
    parcel_buffer_m: float = 3.0,
    hydro_strategy: str = "breach_then_fill",
) -> None:
    """Build one pipeline artifact: DEM → pointer → accum → mask → verify
    → extract streams → filter reachable → binary export.

    Parameters
    ----------
    resolution : float
        DEM resolution in meters (1.0 or 10.0).
    algorithm : str
        'd8' or 'dinf'.
    stream_threshold : int
        Accumulation cell count for WBT extract_streams.
    threshold_frac : float or None
        If provided, overrides stream_threshold.  Fraction of masked
        contributing area cells (e.g. 0.0001 = 0.01%).  Converts to
        absolute cell count from the masked accumulation raster.
    parcel_buffer_m : float
        Buffer distance in meters around the parcel for reachability
        filtering (registration tolerance between parcel boundary and DEM).
    hydro_strategy : str
        DEM preprocessing strategy: 'breach_then_fill' (default),
        'fill_only', or 'breach_only'.
    """
    assert algorithm in ("d8", "dinf"), f"Unknown algorithm: {algorithm}"
    res_tag = f"{int(resolution)}m"
    is_1m = resolution == 1.0

    DERIVED.mkdir(parents=True, exist_ok=True)

    # --- File paths ---
    suffix = "_f32" if is_1m else ""
    dem_filled = DERIVED / f"dem_{res_tag}_filled{suffix}.tif"
    dem_raw = DERIVED / f"dem_{res_tag}_clipped.tif"

    ptr_name = "dinf_pointer" if algorithm == "dinf" else "d8_pointer"
    accum_name = "dinf_flow_accum" if algorithm == "dinf" else "d8_flow_accum"
    ptr = DERIVED / f"{ptr_name}_{res_tag}.tif"
    accum = DERIVED / f"{accum_name}_{res_tag}.tif"
    accum_masked = DERIVED / f"{accum_name}_{res_tag}_masked.tif"
    streams = DERIVED / f"streams_{algorithm}_{res_tag}_{stream_threshold}.tif"

    binary_name = _BINARY_NAMES[(resolution, algorithm)]
    binary = MAPS / binary_name

    # --- DEM fetch + preprocess ---
    if not dem_filled.exists():
        raw = fetch_dem(CONTRIBUTING_AREA, resolution=resolution,
                        crs=TARGET_CRS, buffer_m=200, output=dem_raw)
        dem_filled = preprocess_dem(raw, output=dem_filled,
                                    strategy=hydro_strategy)

    # --- Flow direction + accumulation ---
    if algorithm == "dinf":
        compute_dinf(dem_filled, output=accum, pointer=ptr)
    else:
        compute_d8_pointer(dem_filled, output=ptr)
        compute_d8_accum(dem_filled, output=accum, pointer=ptr,
                         backend="wbt_ptr_pyflwdir")

    # --- Mask + verify ---
    accum_masked = _mask_to_boundary(accum, CONTRIBUTING_AREA, accum_masked)
    verify_accumulation(accum_masked)
    verify_monotonicity_along_paths(accum_masked, ptr,
                                    pointer_type=algorithm)

    # Convert threshold_frac to absolute cell count if provided
    if threshold_frac is not None:
        with rasterio.open(accum_masked) as src:
            n_contrib = int((src.read(1) > 0).sum())
        stream_threshold = max(1, int(n_contrib * threshold_frac))

    # --- Stream extraction + reachability + export ---
    extract_streams(accum_masked, threshold=stream_threshold,
                    output=streams)
    streams = filter_reachable(streams, ptr, PARCEL,
                               pointer_type=algorithm,
                               buffer_m=parcel_buffer_m)
    _export_binary(streams, accum_masked, binary,
                   boundary=CONTRIBUTING_AREA)


# -- CLI --

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build parcel-centered stream morphology artifacts.")
    parser.add_argument(
        "command", nargs="?",
        choices=["dinf1m", "dinf10m", "d81m", "d810m", "all"],
        help="Which artifact to build.")
    parser.add_argument(
        "--threshold", type=int, default=250,
        help="Stream extraction accumulation threshold in cells (default: 250).")
    parser.add_argument(
        "--threshold-frac", type=float, default=None,
        help="Stream extraction threshold as fraction of contributing area cells "
             "(e.g. 0.0001 for 0.01%%). Overrides --threshold.")
    parser.add_argument(
        "--buffer", type=float, default=3.0,
        help="Parcel buffer in meters for reachability filtering (default: 3.0).")
    parser.add_argument(
        "--hydro", choices=["breach_then_fill", "fill_only", "breach_only"],
        default="breach_then_fill",
        help="DEM preprocessing strategy (default: breach_then_fill).")
    args = parser.parse_args()

    if args.command is None:
        parser.print_usage()
        sys.exit(1)

    def run(resolution, algorithm):
        build(resolution, algorithm,
              stream_threshold=args.threshold,
              threshold_frac=args.threshold_frac,
              parcel_buffer_m=args.buffer,
              hydro_strategy=args.hydro)

    COMMANDS = {
        "dinf1m":  lambda: run(1.0, "dinf"),
        "dinf10m": lambda: run(10.0, "dinf"),
        "d81m":    lambda: run(1.0, "d8"),
        "d810m":   lambda: run(10.0, "d8"),
    }

    if args.command == "all":
        for fn in COMMANDS.values():
            fn()
    else:
        COMMANDS[args.command]()
