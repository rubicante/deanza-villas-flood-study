"""
Project-specific: De Anza Villas parcel contributing area — four artifacts
for the threshold morph explorer. Thin CLI over the deliverable library.

Owns the binary export format and CRS conversion that the explorer needs.
"""

import argparse
import shutil
import struct
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import geopandas as gpd
import rasterio
from rasterio.warp import transform as rio_transform

from deliverable import (
    fetch_dem_1m, fetch_dem_10m, preprocess_dem,
    compute_d8_pointer, compute_d8_accum,
    compute_dinf,
    extract_streams,
    verify_accumulation, verify_monotonicity_along_paths,
)
from deliverable.parcels import generate_deanza_villas
from deliverable.reachability import filter_reachable
from deliverable.upstream import contributing_area

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "derived" / "vectors"
MAPS = ROOT / "outputs" / "maps"
DERIVED = ROOT / "data" / "derived" / "rasters"
TARGET_CRS = "EPSG:5070"

PARCEL = ROOT / "data" / "raw" / "vectors" / "deanza_villas_boundary.geojson"
CONTRIBUTING_AREA = DATA / "parcel_contributing_area.geojson"
CONTRIBUTING_AREA_5070 = DATA / "parcel_contributing_area_5070.geojson"
REACHABILITY_TARGET = ROOT / "data" / "raw" / "vectors" / "deanza_villas_boundary.geojson"
_BOOTSTRAP_BUFFER_M = 25_000.0
_BOOTSTRAP_DIR = ROOT / "data" / "derived" / "bootstrap"


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
    fraction_raster: Path | None = None,
) -> Path:
    """Export sorted binary for explorer: uint32 header + stride-3 float32.

    If fraction_raster is provided, its values replace accumulation as the
    sort key (for flow-weighted reachability where values are 0.0–1.0
    fractions rather than raw accumulation counts)."""
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

    # Use fraction raster as sort key if provided
    if fraction_raster is not None:
        with rasterio.open(fraction_raster) as src_frac:
            frac_data = src_frac.read(1)
        sort_values = frac_data[rows, cols]
    else:
        sort_values = accum_data[rows, cols]

    order = np.argsort(sort_values)[::-1]
    sort_values = sort_values[order]
    lons = lons[order]
    lats = lats[order]

    assert np.sum(np.isinf(sort_values)) == 0, "inf in export"
    assert np.sum(np.isnan(sort_values)) == 0, "nan in export"

    with open(output, "wb") as f:
        f.write(struct.pack("I", 0x48465342))  # magic: "HFSB"
        f.write(struct.pack("I", 1))            # version
        f.write(struct.pack("I", n_cells))
        for i in range(n_cells):
            f.write(struct.pack("fff", float(sort_values[i]), float(lons[i]),
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


# -- Prepare (contributing area) --

def prepare(parcel_fn: Callable[[], Path] | None = None) -> None:
    """Fetch 10m DEM superset, compute contributing area, save GeoJSONs, clean up."""
    if CONTRIBUTING_AREA.exists():
        print(f"Contributing area exists — delete to rerun:\n  {CONTRIBUTING_AREA}")
        return

    DATA.mkdir(parents=True, exist_ok=True)
    MAPS.mkdir(parents=True, exist_ok=True)
    _BOOTSTRAP_DIR.mkdir(parents=True, exist_ok=True)

    if not PARCEL.exists():
        if parcel_fn is None:
            raise RuntimeError(
                f"Parcel boundary not found: {PARCEL}\n"
                "Pass a parcel_fn to prepare() or run fetch_parcel_deanza_villas.py."
            )
        parcel_fn()

    parcel = gpd.read_file(PARCEL)
    parcel_buffered = gpd.GeoDataFrame(
        geometry=parcel.to_crs(TARGET_CRS).buffer(_BOOTSTRAP_BUFFER_M),
        crs=TARGET_CRS,
    )

    dem_raw    = _BOOTSTRAP_DIR / "dem_10m.tif"
    dem_filled = _BOOTSTRAP_DIR / "dem_10m_filled.tif"
    ptr        = _BOOTSTRAP_DIR / "dinf_pointer_10m.tif"

    print("=== prepare: fetch 10m DEM ===")
    if not dem_raw.exists():
        fetch_dem_10m(parcel_buffered, output=dem_raw)

    print("\n=== prepare: preprocess ===")
    if not dem_filled.exists():
        preprocess_dem(dem_raw, output=dem_filled, strategy="breach_then_fill")

    print("\n=== prepare: D∞ pointer ===")
    if not ptr.exists():
        compute_dinf(dem_filled, output=_BOOTSTRAP_DIR / "dinf_accum_10m.tif", pointer=ptr)

    print("\n=== prepare: contributing area BFS ===")
    gdf_4326 = contributing_area(ptr, parcel, output_mask=_BOOTSTRAP_DIR / "ca_mask.tif")

    gdf_5070 = gdf_4326.to_crs(TARGET_CRS)
    gdf_5070.geometry = gdf_5070.geometry.buffer(10.0)  # absorb 10m cell quantization
    gdf_5070.to_file(CONTRIBUTING_AREA_5070, driver="GeoJSON")
    gdf_5070.to_crs("EPSG:4326").to_file(CONTRIBUTING_AREA, driver="GeoJSON")
    shutil.copy(CONTRIBUTING_AREA, MAPS / CONTRIBUTING_AREA.name)
    print(f"  Contributing area: {gdf_5070.iloc[0].get('area_km2', '?')} km²")

    shutil.rmtree(_BOOTSTRAP_DIR)
    print("  Temporary superset removed.")


# -- Build --

def build(
    resolution: float,
    algorithm: str,
    *,
    stream_threshold: int = 250,
    threshold_frac: float | None = None,
    hydro_strategy: str = "breach_then_fill",
    reachability_mode: str = "boolean",
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
    hydro_strategy : str
        DEM preprocessing strategy: 'breach_then_fill' (default),
        'fill_only', or 'breach_only'.
    """
    assert algorithm in ("d8", "dinf"), f"Unknown algorithm: {algorithm}"
    if reachability_mode == "flow_weighted" and algorithm == "d8":
        print("  Note: flow-weighted reachability with D8 is equivalent to "
              "boolean (single-path fractions are always 0 or 1)")
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
    if reachability_mode == "flow_weighted":
        binary_name = binary_name.replace(".bin", "_frac.bin")
    binary = MAPS / binary_name

    if binary.exists():
        print(f"  cached: {binary}")
        return

    # --- DEM fetch + preprocess ---
    if not dem_filled.exists():
        fetch_fn = fetch_dem_1m if resolution == 1.0 else fetch_dem_10m
        raw = fetch_fn(CONTRIBUTING_AREA, output=dem_raw, crs=TARGET_CRS)
        try:
            dem_filled = preprocess_dem(raw, output=dem_filled,
                                        strategy=hydro_strategy)
        except RuntimeError as e:
            print(f"  WARNING: preprocess failed for {res_tag} {algorithm} — skipping: {e}")
            return

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
    reachable = DERIVED / f"reachable_{algorithm}_{res_tag}.tif"
    result = filter_reachable(streams, ptr, REACHABILITY_TARGET,
                              output=reachable,
                              pointer_type=algorithm,
                              reachability_mode=reachability_mode)
    streams = result.streams
    _export_binary(streams, accum_masked, binary,
                   boundary=CONTRIBUTING_AREA,
                   fraction_raster=result.fractions)


# -- Clean --

def clean() -> None:
    """Delete computed artifacts so they will be regenerated on next run.
    Does not touch cached DEM tiles, raw vectors, or tracked outputs/maps files."""
    for d in [DERIVED, DATA]:
        if d.exists():
            shutil.rmtree(d)
            print(f"  removed {d}")
    for f in MAPS.glob("*.bin"):
        f.unlink()
        print(f"  removed {f}")


def clean_all() -> None:
    """Delete all derived data including cached DEM tiles."""
    clean()
    tile_cache = ROOT / "data" / "raw" / "dem" / "tiles"
    if tile_cache.exists():
        shutil.rmtree(tile_cache)
        print(f"  removed {tile_cache}")


# -- CLI --

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build parcel-centered stream morphology artifacts.")
    parser.add_argument(
        "command", nargs="?",
        choices=["prepare", "dinf1m", "dinf10m", "d81m", "d810m", "all", "clean", "clean-all"],
        help="Which step to run.")
    parser.add_argument(
        "--threshold", type=int, default=250,
        help="Stream extraction accumulation threshold in cells (default: 250).")
    parser.add_argument(
        "--threshold-frac", type=float, default=None,
        help="Stream extraction threshold as fraction of contributing area cells "
             "(e.g. 0.0001 for 0.01%%). Overrides --threshold.")
    parser.add_argument(
        "--hydro", choices=["breach_then_fill", "fill_only", "breach_only"],
        default="breach_then_fill",
        help="DEM preprocessing strategy (default: breach_then_fill).")
    parser.add_argument(
        "--reachability", choices=["boolean", "flow_weighted"],
        default="boolean",
        help="Reachability mode: boolean (default) or flow_weighted (D∞ only).")
    args = parser.parse_args()

    if args.command is None:
        parser.print_usage()
        sys.exit(1)

    def run(resolution, algorithm):
        build(resolution, algorithm,
              stream_threshold=args.threshold,
              threshold_frac=args.threshold_frac,
              hydro_strategy=args.hydro,
              reachability_mode=args.reachability)

    COMMANDS = {
        "prepare":   lambda: prepare(parcel_fn=generate_deanza_villas),
        "dinf1m":    lambda: run(1.0, "dinf"),
        "dinf10m":   lambda: run(10.0, "dinf"),
        "d81m":      lambda: run(1.0, "d8"),
        "d810m":     lambda: run(10.0, "d8"),
        "clean":     clean,
        "clean-all": clean_all,
    }

    if args.command == "all":
        prepare()
        for name, fn in COMMANDS.items():
            if name not in ("prepare", "clean", "clean-all"):
                fn()
    else:
        COMMANDS[args.command]()
