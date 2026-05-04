from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd

from scripts.init_env import load_env
from scripts.study_config import (
    ROOT,
    config_path,
    deliverable_path,
    step_path,
)
from scripts.study_utils import build_standard_map, ensure_crs, optional

STREAMS_PATH = config_path("paths", "selected_streams")
PARCEL_BOUNDARY_PATH = config_path("paths", "parcel_boundary")
PARCEL_POLYGONS_PATH = config_path("paths", "parcel_polygons")
HAZARD_PATH = config_path("paths", "hazard_polygons")
LOCAL_AOI_PATH = config_path("paths", "local_aoi")
CONTEXT_AOI_PATH = config_path("paths", "context_aoi")
OUTDIR = step_path("parcel_overlay", "outdir")
REPORT_PATH = deliverable_path("parcel_overlay_report")
MAP_PATH = deliverable_path("parcel_overlay_map")


@dataclass
class OverlayStats:
    layer_name: str
    total_length_m: float
    inside_parcel_m: float
    inside_hazard_m: float
    inside_parcel_and_hazard_m: float
    outside_parcel_m: float
    parcel_share: float
    hazard_share: float
    hazard_share_within_parcel: float
    segments: int
    segments_touching_parcel: int
    segments_touching_hazard: int
    segments_touching_both: int


def compute_overlay_metrics(
    streams: gpd.GeoDataFrame,
    parcel_boundary: gpd.GeoDataFrame,
    parcel_polygons: gpd.GeoDataFrame,
    hazard: gpd.GeoDataFrame,
    local_aoi: gpd.GeoDataFrame,
    context_aoi: gpd.GeoDataFrame,
    outdir: Path,
    clip_outputs: bool = True,
) -> tuple[pd.DataFrame, Path, Path, Path | None]:
    """Compute overlay metrics and write CSV/JSON to outdir. Returns (df, metrics_csv, metrics_json, clipped_gpkg)."""
    parcel_union = parcel_boundary.geometry.union_all()
    hazard_union = hazard.geometry.union_all()

    segs = streams[streams.geometry.notna()].copy()
    segs = segs[~segs.geometry.is_empty].copy()
    segs["length_m"] = segs.geometry.length
    segs["parcel_len_m"] = segs.geometry.intersection(parcel_union).length
    segs["hazard_len_m"] = segs.geometry.intersection(hazard_union).length
    segs["parcel_hazard_len_m"] = segs.geometry.intersection(parcel_union.intersection(hazard_union)).length
    segs["local_aoi_len_m"] = segs.geometry.intersection(local_aoi.geometry.union_all()).length
    segs["context_len_m"] = segs.geometry.intersection(context_aoi.geometry.union_all()).length
    segs["touches_parcel"] = segs["parcel_len_m"] > 0
    segs["touches_hazard"] = segs["hazard_len_m"] > 0
    segs["touches_both"] = segs["parcel_hazard_len_m"] > 0

    total_length = float(segs["length_m"].sum())
    parcel_length = float(segs["parcel_len_m"].sum())
    hazard_length = float(segs["hazard_len_m"].sum())
    parcel_hazard_length = float(segs["parcel_hazard_len_m"].sum())

    df = pd.DataFrame([
        asdict(OverlayStats(
            layer_name="selected_stream_network",
            total_length_m=total_length,
            inside_parcel_m=parcel_length,
            inside_hazard_m=hazard_length,
            inside_parcel_and_hazard_m=parcel_hazard_length,
            outside_parcel_m=total_length - parcel_length,
            parcel_share=(parcel_length / total_length) if total_length else 0.0,
            hazard_share=(hazard_length / total_length) if total_length else 0.0,
            hazard_share_within_parcel=(parcel_hazard_length / parcel_length) if parcel_length else 0.0,
            segments=int(len(segs)),
            segments_touching_parcel=int(segs["touches_parcel"].sum()),
            segments_touching_hazard=int(segs["touches_hazard"].sum()),
            segments_touching_both=int(segs["touches_both"].sum()),
        ))
    ])

    outdir.mkdir(parents=True, exist_ok=True)
    metrics_csv = outdir / "parcel_overlay_metrics.csv"
    metrics_json = outdir / "parcel_overlay_metrics.json"
    df.to_csv(metrics_csv, index=False)
    metrics_json.write_text(json.dumps(df.to_dict(orient="records"), indent=2))

    clipped_gpkg: Path | None = None
    if clip_outputs:
        inside = segs[segs["parcel_len_m"] > 0].copy()
        clipped_gpkg = outdir / "deanza_villas_2km_1m_dem_filled_streams_5000_in_parcel.gpkg"
        if clipped_gpkg.exists():
            clipped_gpkg.unlink()
        inside = inside.drop(columns=["touches_parcel", "touches_hazard", "touches_both"])
        inside.to_file(clipped_gpkg, driver="GPKG")

    return df, metrics_csv, metrics_json, clipped_gpkg


def write_report(
    df: pd.DataFrame,
    report_path: Path,
    streams_path: Path,
    parcel_boundary: gpd.GeoDataFrame,
    parcel_polygons: gpd.GeoDataFrame,
    hazard: gpd.GeoDataFrame,
    metrics_csv: Path,
    metrics_json: Path,
    clipped_gpkg: Path | None,
) -> None:
    row = df.iloc[0]
    _clipped = clipped_gpkg.relative_to(ROOT) if clipped_gpkg is not None else None
    clipped_line = optional("\nClipped parcel-only stream layer: `{}`\n", _clipped)
    clipped_output = optional("- Parcel-only stream GPKG: `{}`\n", _clipped)

    report = f"""\
# Parcel Overlay

This step wired the authoritative De Anza Villas parcel geometry into the selected 5000-cell channel network and re-ran the overlay metrics against the hazard and fan-context layers.

## Inputs used
- Selected stream network: `{streams_path.relative_to(ROOT)}`
- Parcel boundary: `{PARCEL_BOUNDARY_PATH.relative_to(ROOT)}`
- Parcel polygons: `{PARCEL_POLYGONS_PATH.relative_to(ROOT)}` ({len(parcel_polygons)} features)
- Hazard polygons: `{HAZARD_PATH.relative_to(ROOT)}` ({len(hazard)} features)
- Local AOI: `{LOCAL_AOI_PATH.relative_to(ROOT)}`
- Context AOI: `{CONTEXT_AOI_PATH.relative_to(ROOT)}`

## Parcel-aware overlay metrics

```csv
{df.to_csv(index=False).rstrip()}
```

Key readout:
- network length inside parcel boundary: {row['inside_parcel_m']:.1f} m ({row['parcel_share']:.1%})
- network length inside mapped hazard polygons: {row['inside_hazard_m']:.1f} m ({row['hazard_share']:.1%})
- network length inside both parcel boundary and hazard polygons: {row['inside_parcel_and_hazard_m']:.1f} m
- hazard share within parcel boundary: {row['hazard_share_within_parcel']:.1%}
- segments touching parcel boundary: {int(row['segments_touching_parcel'])} of {int(row['segments'])}
- segments touching hazard polygons: {int(row['segments_touching_hazard'])} of {int(row['segments'])}
- segments touching both parcel and hazard: {int(row['segments_touching_both'])} of {int(row['segments'])}
{clipped_line}
## Interpretation

- The authoritative boundary confirms how much of the selected drainage network actually crosses or sits within the De Anza Villas parcel complex.
- Comparing the network to the dissolved parcel boundary avoids using a hand-drawn approximation for parcel-scale risk context.
- The hazard overlap remains substantial after parcel-aware clipping, so the parcel context does not eliminate the channel/wash signal; it localizes it.
- The parcel polygons are preserved as a separate layer for later per-APN interrogation, while the dissolved boundary is the canonical single-file parcel geometry.

## Context caveat

These are terrain-derived and parcel-overlay context metrics, not a licensed engineering flood determination or FEMA map revision.

## Outputs

- Metrics CSV: `{metrics_csv.relative_to(ROOT)}`
- Metrics JSON: `{metrics_json.relative_to(ROOT)}`
{clipped_output}- Canonical parcel boundary: `{PARCEL_BOUNDARY_PATH.relative_to(ROOT)}`
- Parcel polygon set: `{PARCEL_POLYGONS_PATH.relative_to(ROOT)}`
- Canonical parcel overlay map: `{MAP_PATH.relative_to(ROOT)}`
"""

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")


def main() -> None:
    load_env()

    # Read all vectors once; pass GeoDataFrames to all downstream functions.
    streams = ensure_crs(gpd.read_file(STREAMS_PATH))
    parcel_boundary = ensure_crs(gpd.read_file(PARCEL_BOUNDARY_PATH))
    parcel_polygons = ensure_crs(gpd.read_file(PARCEL_POLYGONS_PATH))
    hazard = ensure_crs(gpd.read_file(HAZARD_PATH))
    local_aoi = ensure_crs(gpd.read_file(LOCAL_AOI_PATH))
    context_aoi = ensure_crs(gpd.read_file(CONTEXT_AOI_PATH))

    df, metrics_csv, metrics_json, clipped_gpkg = compute_overlay_metrics(
        streams=streams,
        parcel_boundary=parcel_boundary,
        parcel_polygons=parcel_polygons,
        hazard=hazard,
        local_aoi=local_aoi,
        context_aoi=context_aoi,
        outdir=OUTDIR,
    )

    write_report(
        df=df,
        report_path=REPORT_PATH,
        streams_path=STREAMS_PATH,
        parcel_boundary=parcel_boundary,
        parcel_polygons=parcel_polygons,
        hazard=hazard,
        metrics_csv=metrics_csv,
        metrics_json=metrics_json,
        clipped_gpkg=clipped_gpkg,
    )

    map_streams = clipped_gpkg if clipped_gpkg is not None and clipped_gpkg.exists() else STREAMS_PATH
    m = build_standard_map(
        center_gdf=parcel_boundary,
        zoom=16,
        hazard=hazard,
        context_aoi=context_aoi,
        local_aoi=local_aoi,
        parcel_polygons=parcel_polygons,
        parcel_boundary=parcel_boundary,
        streams=ensure_crs(gpd.read_file(map_streams)) if map_streams != STREAMS_PATH else streams,
    )
    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(MAP_PATH))

    print(REPORT_PATH)
    print(metrics_csv)
    print(metrics_json)
    if clipped_gpkg is not None:
        print(clipped_gpkg)
    print(MAP_PATH)


if __name__ == "__main__":
    main()
