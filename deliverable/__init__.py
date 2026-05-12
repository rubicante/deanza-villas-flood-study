"""
Portable DEM/hydrology pipeline: fetch, condition, D8, D∞, streams, verify.

Public API:
    from deliverable import (
        fetch_dem, preprocess_dem,
        compute_d8_pointer, compute_d8_accum,
        compute_dinf,
        extract_streams, export_geojson,
        verify_accumulation, check_d8_dinf_agreement,
    )

All functions take pathlib.Path arguments and return pathlib.Path outputs.
They raise on failure -- no return-code patterns.
"""
from deliverable.fetch import fetch_dem
from deliverable.preprocess import preprocess_dem
from deliverable.d8 import compute_d8_pointer, compute_d8_accum
from deliverable.dinf import compute_dinf
from deliverable.streams import extract_streams, export_geojson
from deliverable.verify import verify_accumulation, verify_monotonicity_along_paths

__all__ = [
    "fetch_dem", "preprocess_dem",
    "compute_d8_pointer", "compute_d8_accum",
    "compute_dinf",
    "extract_streams", "export_geojson",
    "verify_accumulation", "verify_monotonicity_along_paths",
]
