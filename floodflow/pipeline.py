"""
Parcel contributing area → stream datasets for the explorer.

    prepare(layout)          parcel → 10m D∞ contributing area (+ publish layers)
    build(layout, params)    DEM → pointer → accum → mask → verify → streams → binary
    clean(root) / clean_all(root)

Paths come from `Layout`, dataset settings from `BuildParams` (see config.py);
the binary format and manifest live in publish.py. The CLI is cli.py.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio

from floodflow.config import (
    BOOTSTRAP_BUFFER_M,
    DEFAULT_PARCEL,
    ROOT,
    TARGET_CRS,
    BuildParams,
    Layout,
)
from floodflow.d8 import compute_d8_accum, compute_d8_pointer
from floodflow.dinf import compute_dinf
from floodflow.fetch import fetch_dem_1m, fetch_dem_10m, provenance_path, read_provenance
from floodflow.geo import polygon_mask
from floodflow.preprocess import preprocess_dem
from floodflow.publish import (
    export_binary,
    publish_parcel_layers,
    published_params,
    record_dataset,
    unpublish_datasets,
)
from floodflow.streams import extract_streams
from floodflow.upstream import contributing_area
from floodflow.verify import verify_accumulation, verify_monotonicity_along_paths

# -- Helpers --

def _mask_to_boundary(raster_path: Path, boundary: Path,
                      output_path: Path) -> Path:
    """Mask a raster to a GeoJSON boundary polygon. Returns output Path."""
    with rasterio.open(raster_path) as src:
        data = src.read(1)
        prof = src.profile.copy()
    mask = polygon_mask(boundary, prof["crs"], prof["transform"], data.shape)
    masked = np.where(mask, data, 0).astype(prof["dtype"])
    with rasterio.open(output_path, "w", **prof) as dst:
        dst.write(masked, 1)
    return output_path


# -- Prepare (contributing area) --

def prepare(layout: Layout) -> None:
    """Fetch 10m DEM superset, compute contributing area, save GeoJSONs, clean up.

    Generates the parcel boundary if it is missing. Always republishes the
    parcel's boundary and contributing area to docs/data/<parcel>/, even
    when the contributing area is cached."""
    if layout.contributing_area.exists():
        print(f"Contributing area exists — delete to rerun:\n  {layout.contributing_area}")
        publish_parcel_layers(layout)
        return

    layout.vectors.mkdir(parents=True, exist_ok=True)
    layout.bootstrap.mkdir(parents=True, exist_ok=True)

    if not layout.boundary.exists():
        layout.parcel.generate(layout.boundary)

    parcel = gpd.read_file(layout.boundary)
    parcel_buffered = gpd.GeoDataFrame(
        geometry=parcel.to_crs(TARGET_CRS).buffer(BOOTSTRAP_BUFFER_M),
        crs=TARGET_CRS,
    )

    dem_raw    = layout.bootstrap / "dem_10m.tif"
    dem_filled = layout.bootstrap / "dem_10m_filled.tif"
    ptr        = layout.bootstrap / "dinf_pointer_10m.tif"

    print("=== prepare: fetch 10m DEM ===")
    if not dem_raw.exists():
        fetch_dem_10m(parcel_buffered, output=dem_raw)

    print("\n=== prepare: preprocess ===")
    if not dem_filled.exists():
        preprocess_dem(dem_raw, output=dem_filled, strategy="breach_then_fill")

    print("\n=== prepare: D∞ pointer ===")
    if not ptr.exists():
        compute_dinf(dem_filled, output=layout.bootstrap / "dinf_accum_10m.tif", pointer=ptr)

    print("\n=== prepare: contributing area BFS ===")
    gdf_4326 = contributing_area(ptr, parcel, output_mask=layout.bootstrap / "ca_mask.tif")

    gdf_5070 = gdf_4326.to_crs(TARGET_CRS)
    gdf_5070.geometry = gdf_5070.geometry.buffer(10.0)  # absorb 10m cell quantization
    gdf_5070.to_file(layout.contributing_area_5070, driver="GeoJSON")
    gdf_5070.to_crs("EPSG:4326").to_file(layout.contributing_area, driver="GeoJSON")
    # Keep the bootstrap DEM's provenance with the contributing area; the
    # bootstrap directory is deleted below.
    shutil.copy(provenance_path(dem_raw), provenance_path(layout.contributing_area))
    publish_parcel_layers(layout)
    print(f"  Contributing area: {gdf_5070.iloc[0].get('area_km2', '?')} km²")

    shutil.rmtree(layout.bootstrap)
    print("  Temporary superset removed.")


# -- Build --

def build(layout: Layout, params: BuildParams) -> None:
    """Build one published dataset: DEM → pointer → accum → mask → verify
    → extract streams → (optional reachability) → binary export.

    Skips when the manifest already records this dataset with identical
    params. `params.threshold_frac`, if set, overrides `stream_threshold`
    as a fraction of contributing-area cells (e.g. 0.0001 = 0.01%)."""
    if params.reachability_mode == "flow_weighted" and params.algorithm == "d8":
        print("  Note: flow-weighted reachability with D8 is equivalent to "
              "boolean (single-path fractions are always 0 or 1)")
    res_tag = params.res_tag
    algorithm = params.algorithm
    derived = layout.rasters
    derived.mkdir(parents=True, exist_ok=True)

    # --- File paths ---
    suffix = "_f32" if params.resolution_m == 1.0 else ""
    dem_filled = derived / f"dem_{res_tag}_{params.hydro_strategy}{suffix}.tif"
    dem_raw = derived / f"dem_{res_tag}_clipped.tif"

    ptr_name = "dinf_pointer" if algorithm == "dinf" else "d8_pointer"
    accum_name = "dinf_flow_accum" if algorithm == "dinf" else "d8_flow_accum"
    ptr = derived / f"{ptr_name}_{res_tag}.tif"
    accum = derived / f"{accum_name}_{res_tag}.tif"
    accum_masked = derived / f"{accum_name}_{res_tag}_masked.tif"
    binary = layout.publish_dir / params.binary_name

    if published_params(layout, params) == params.to_dict():
        print(f"  cached: {binary}")
        return

    # --- DEM fetch + preprocess ---
    if not dem_filled.exists():
        fetch_fn = fetch_dem_1m if params.resolution_m == 1.0 else fetch_dem_10m
        raw = fetch_fn(layout.contributing_area, output=dem_raw, crs=TARGET_CRS)
        try:
            dem_filled = preprocess_dem(raw, output=dem_filled,
                                        strategy=params.hydro_strategy)
        except RuntimeError as e:
            print(f"  WARNING: preprocess failed for {res_tag} {algorithm} — skipping: {e}")
            return

    # --- Flow direction + accumulation ---
    if algorithm == "dinf":
        compute_dinf(dem_filled, output=accum, pointer=ptr)
    else:
        compute_d8_pointer(dem_filled, output=ptr)
        compute_d8_accum(dem_filled, output=accum, pointer=ptr)

    # --- Mask + verify ---
    accum_masked = _mask_to_boundary(accum, layout.contributing_area, accum_masked)
    verify_accumulation(accum_masked)
    verify_monotonicity_along_paths(accum_masked, ptr, pointer_type=algorithm)

    # Convert threshold_frac to absolute cell count if provided
    stream_threshold = params.stream_threshold
    if params.threshold_frac is not None:
        with rasterio.open(accum_masked) as src:
            n_contrib = int((src.read(1) > 0).sum())
        stream_threshold = max(1, int(n_contrib * params.threshold_frac))
    streams = derived / f"streams_{algorithm}_{res_tag}_{stream_threshold}.tif"

    # --- Stream extraction + reachability + export ---
    extract_streams(accum_masked, threshold=stream_threshold, output=streams)
    if params.reachability_mode == "none":
        info = export_binary(streams, accum_masked, binary,
                             boundary=layout.contributing_area)
    else:
        from floodflow.experimental.reachability import filter_reachable
        reachable = derived / f"reachable_{algorithm}_{res_tag}.tif"
        result = filter_reachable(streams, ptr, layout.boundary,
                                  output=reachable,
                                  pointer_type=algorithm,
                                  reachability_mode=params.reachability_mode)
        info = export_binary(result.streams, accum_masked, binary,
                             boundary=layout.contributing_area,
                             fraction_raster=result.fractions)
    info["dem"] = read_provenance(dem_raw)
    record_dataset(layout, params, binary, info)


# -- Clean --

def clean(root: Path = ROOT) -> None:
    """Delete computed artifacts so they will be regenerated on next run.
    Does not touch cached DEM tiles, raw vectors, parcel layers, or the
    reference layers in docs/data/."""
    layout = Layout.for_parcel(DEFAULT_PARCEL, root)  # only root-level paths used
    if layout.runs_root.exists():
        shutil.rmtree(layout.runs_root)
        print(f"  removed {layout.runs_root}")
    unpublish_datasets(layout)


def clean_all(root: Path = ROOT) -> None:
    """Delete all derived data including cached DEM tiles."""
    clean(root)
    tile_cache = Path(root) / "data" / "raw" / "dem" / "tiles"
    if tile_cache.exists():
        shutil.rmtree(tile_cache)
        print(f"  removed {tile_cache}")
