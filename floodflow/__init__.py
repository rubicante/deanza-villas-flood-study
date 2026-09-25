"""
Portable DEM/hydrology pipeline: fetch, condition, D8, D∞, streams, verify.

Public API:
    from floodflow import (
        fetch_dem_1m, fetch_dem_10m, preprocess_dem,
        compute_d8_pointer, compute_d8_accum,
        compute_dinf,
        extract_streams,
        verify_accumulation, check_d8_dinf_agreement,
    )

All functions take pathlib.Path arguments and return pathlib.Path outputs.
They raise on failure -- no return-code patterns.
"""
from importlib import import_module

# Resolved on first use (PEP 562), so importing one submodule — e.g.
# floodflow.hydraulics on a remote machine — doesn't pull in rasterio/WBT.
_EXPORTS = {
    "compute_d8_accum": "d8", "compute_d8_pointer": "d8",
    "compute_dinf": "dinf",
    "fetch_dem_1m": "fetch", "fetch_dem_10m": "fetch",
    "preprocess_dem": "preprocess",
    "extract_streams": "streams",
    "verify_accumulation": "verify", "verify_monotonicity_along_paths": "verify",
}
__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name in _EXPORTS:
        return getattr(import_module(f"floodflow.{_EXPORTS[name]}"), name)
    raise AttributeError(f"module 'floodflow' has no attribute {name!r}")
