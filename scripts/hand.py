from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from whitebox.whitebox_tools import WhiteboxTools

from scripts.init_env import load_env
from scripts.study_config import TARGET_CRS, config_path, step_path
from scripts.study_utils import ensure_crs, safe_write_json

DEM_PATH = config_path("paths", "dem_filled")
D8_ACCUM_PATH = config_path("paths", "d8_flow_accum")
D8_POINTER_PATH = config_path("paths", "d8_pointer")
LOCAL_AOI_PATH = config_path("paths", "local_aoi")
PARCEL_BOUNDARY_PATH = config_path("paths", "parcel_boundary")
OUTDIR = step_path("hand", "outdir")
HAND_PATH = step_path("hand", "raster")
STATS_PATH = step_path("hand", "stats_json")
STREAM_THRESHOLD = 5000
STREAM_RASTER = step_path("wash_extraction", "outdir") / f"{DEM_PATH.stem}_streams_{STREAM_THRESHOLD}.tif"
STREAM_VECTOR = config_path("paths", "selected_streams")

INTERPRETATION_NOTE = (
    "HAND is a relative terrain-position index above the selected drainage network, "
    "not an inundation-depth estimate. On active alluvial fans, future storm flow may "
    "avulse away from the nearest mapped drainage; use these values only as terrain "
    "evidence for where channel avulsion or concentrated flow could affect the parcel."
)


@dataclass
class HandZoneStats:
    zone: str
    cells: int
    negative_cells: int
    min_m: float | None
    mean_m: float | None
    max_m: float | None


def _configure_wbt(outdir: Path) -> WhiteboxTools:
    load_env()
    outdir.mkdir(parents=True, exist_ok=True)
    wbt = WhiteboxTools()
    wbt.set_working_dir(str(outdir.resolve()))
    wbt.set_verbose_mode(False)
    return wbt


def ensure_stream_raster(wbt: WhiteboxTools) -> Path:
    """Return the 5000-cell D8 stream raster, deriving it from flow accumulation if needed."""
    if STREAM_RASTER.exists():
        return STREAM_RASTER

    if not D8_ACCUM_PATH.exists():
        raise FileNotFoundError(f"Missing D8 accumulation raster: {D8_ACCUM_PATH}")

    STREAM_RASTER.parent.mkdir(parents=True, exist_ok=True)
    wbt.extract_streams(
        str(D8_ACCUM_PATH.resolve()),
        str(STREAM_RASTER.resolve()),
        STREAM_THRESHOLD,
        zero_background=True,
    )
    return STREAM_RASTER


def compute_hand(wbt: WhiteboxTools, stream_raster: Path) -> Path:
    if not DEM_PATH.exists():
        raise FileNotFoundError(f"Missing filled DEM: {DEM_PATH}")
    HAND_PATH.parent.mkdir(parents=True, exist_ok=True)
    if HAND_PATH.exists():
        HAND_PATH.unlink()
    wbt.elevation_above_stream(
        str(DEM_PATH.resolve()),
        str(stream_raster.resolve()),
        str(HAND_PATH.resolve()),
    )
    if not HAND_PATH.exists():
        raise RuntimeError(f"WhiteboxTools did not create HAND raster: {HAND_PATH}")
    return HAND_PATH


def _valid_hand_values(data: np.ma.MaskedArray | np.ndarray) -> np.ndarray:
    arr = np.ma.masked_invalid(data)
    values = arr.compressed()
    # Whitebox sometimes emits very large sentinels instead of a nodata tag.
    values = values[np.isfinite(values)]
    values = values[np.abs(values) < 1.0e20]
    return values.astype("float64", copy=False)


def _stats_for_values(zone: str, values: np.ndarray) -> HandZoneStats:
    if values.size == 0:
        return HandZoneStats(zone, 0, 0, None, None, None)
    return HandZoneStats(
        zone=zone,
        cells=int(values.size),
        negative_cells=int((values < 0).sum()),
        min_m=float(values.min()),
        mean_m=float(values.mean()),
        max_m=float(values.max()),
    )


def _zone_values(src: rasterio.io.DatasetReader, geometry: Any) -> np.ndarray:
    data = src.read(1, masked=True)
    mask = geometry_mask(
        [geometry],
        out_shape=data.shape,
        transform=src.transform,
        invert=True,
    )
    return _valid_hand_values(np.ma.array(data, mask=np.ma.getmaskarray(data) | ~mask))


def summarize_hand(hand_path: Path) -> dict[str, Any]:
    local_aoi = ensure_crs(gpd.read_file(LOCAL_AOI_PATH))
    parcel = ensure_crs(gpd.read_file(PARCEL_BOUNDARY_PATH))
    local_geom = local_aoi.geometry.union_all()
    parcel_geom = parcel.geometry.union_all()

    with rasterio.open(hand_path) as src:
        raster_crs = src.crs.to_string() if src.crs else None
        all_values = _valid_hand_values(src.read(1, masked=True))
        zones = [
            _stats_for_values("full_hand_raster", all_values),
            _stats_for_values("local_aoi", _zone_values(src, local_geom)),
            _stats_for_values("parcel_boundary", _zone_values(src, parcel_geom)),
        ]
        raster_summary = {
            "path": str(hand_path),
            "crs": raster_crs,
            "width": int(src.width),
            "height": int(src.height),
            "cell_size_x_m": float(src.transform.a),
            "cell_size_y_m": float(abs(src.transform.e)),
            "nodata": None if src.nodata is None else float(src.nodata),
        }

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "WhiteboxTools elevation_above_stream on breached+filled DEM and 5000-cell D8 stream raster.",
        "interpretation_note": INTERPRETATION_NOTE,
        "inputs": {
            "filled_dem": str(DEM_PATH),
            "d8_flow_accumulation": str(D8_ACCUM_PATH),
            "d8_pointer": str(D8_POINTER_PATH),
            "stream_threshold_cells": STREAM_THRESHOLD,
            "stream_raster": str(STREAM_RASTER),
            "stream_vector_reference": str(STREAM_VECTOR),
            "local_aoi": str(LOCAL_AOI_PATH),
            "parcel_boundary": str(PARCEL_BOUNDARY_PATH),
            "target_crs": TARGET_CRS,
        },
        "outputs": {"hand_raster": str(HAND_PATH), "stats_json": str(STATS_PATH)},
        "raster": raster_summary,
        "zones": [asdict(zone) for zone in zones],
        "quality_flags": {
            "negative_hand_cells_total": next(z.negative_cells for z in zones if z.zone == "full_hand_raster"),
            "negative_hand_cells_local_aoi": next(z.negative_cells for z in zones if z.zone == "local_aoi"),
            "negative_hand_cells_parcel": next(z.negative_cells for z in zones if z.zone == "parcel_boundary"),
            "negative_values_flagged": any(z.negative_cells > 0 for z in zones),
        },
    }


def main() -> None:
    wbt = _configure_wbt(OUTDIR)
    stream_raster = ensure_stream_raster(wbt)
    hand_path = compute_hand(wbt, stream_raster)
    summary = summarize_hand(hand_path)
    safe_write_json(summary, STATS_PATH)
    print(f"stream_raster: {stream_raster}")
    print(f"hand_raster:   {hand_path}")
    print(f"hand_stats:    {STATS_PATH}")
    for zone in summary["zones"]:
        print(
            f"{zone['zone']}: cells={zone['cells']} negative={zone['negative_cells']} "
            f"min={zone['min_m']} mean={zone['mean_m']} max={zone['max_m']}"
        )
    print(summary["interpretation_note"])


if __name__ == "__main__":
    main()
