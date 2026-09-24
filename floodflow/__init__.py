"""
Portable DEM/hydrology pipeline: fetch, condition, D8, D∞, streams, verify.

Public API:
    from floodflow import (
        fetch_dem_1m, fetch_dem_10m, preprocess_dem,
        compute_d8_pointer, compute_d8_accum,
        compute_dinf,
        extract_streams, export_geojson,
        verify_accumulation, check_d8_dinf_agreement,
    )

All functions take pathlib.Path arguments and return pathlib.Path outputs.
They raise on failure -- no return-code patterns.
"""
from floodflow.d8 import compute_d8_accum, compute_d8_pointer
from floodflow.dinf import compute_dinf
from floodflow.fetch import fetch_dem_1m, fetch_dem_10m
from floodflow.preprocess import preprocess_dem
from floodflow.streams import export_geojson, extract_streams
from floodflow.verify import verify_accumulation, verify_monotonicity_along_paths

__all__ = [
    "fetch_dem_1m", "fetch_dem_10m", "preprocess_dem",
    "compute_d8_pointer", "compute_d8_accum",
    "compute_dinf",
    "extract_streams", "export_geojson",
    "verify_accumulation", "verify_monotonicity_along_paths",
]
