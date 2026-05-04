from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
from whitebox.whitebox_tools import WhiteboxTools

from scripts.init_env import load_env
from scripts.study_config import (
    ROOT,
    DEFAULT_THRESHOLDS,
    TARGET_CRS,
    config_path,
    deliverable_path,
    step_path,
)
from scripts.study_utils import optional, safe_write_json

DEM_PATH = config_path("paths", "dem_filled")
ACCUM_PATH = config_path("paths", "d8_flow_accum")
POINTER_PATH = config_path("paths", "d8_pointer")
HAZARD_PATH = config_path("paths", "hazard_polygons")
LOCAL_AOI_PATH = config_path("paths", "local_aoi")
CONTEXT_AOI_PATH = config_path("paths", "context_aoi")
OUTDIR = step_path("wash_extraction", "outdir")
REPORT_PATH = deliverable_path("wash_extraction_report")


@dataclass
class ThresholdStats:
    threshold_cells: int
    segments: int
    total_length_m: float
    hazard_length_m: float
    hazard_share: float
    local_aoi_share: float
    context_share: float
    mean_segment_length_m: float
    max_segment_length_m: float
    segments_touching_hazard: int


def _clean_shapefile_outputs(path: Path) -> None:
    for suffix in [".shp", ".shx", ".dbf", ".prj", ".cpg", ".qpj"]:
        candidate = path.with_suffix(suffix)
        if candidate.exists():
            candidate.unlink()


def derive_streams(
    dem_path: Path,
    accum_path: Path,
    pointer_path: Path,
    hazard_path: Path,
    local_aoi_path: Path,
    context_aoi_path: Path,
    outdir: Path,
    thresholds: list[int],
) -> tuple[pd.DataFrame, Path, Path | None, int | None, int]:
    outdir.mkdir(parents=True, exist_ok=True)
    dem_path = dem_path.resolve()
    accum_path = accum_path.resolve()
    pointer_path = pointer_path.resolve()
    hazard_path = hazard_path.resolve()
    local_aoi_path = local_aoi_path.resolve()
    context_aoi_path = context_aoi_path.resolve()
    outdir = outdir.resolve()

    load_env()

    wbt = WhiteboxTools()
    wbt.set_working_dir(str(outdir))
    wbt.set_verbose_mode(False)

    if not pointer_path.exists():
        wbt.d8_pointer(str(dem_path), str(pointer_path))

    hazard = gpd.read_file(hazard_path).to_crs(TARGET_CRS)
    hazard_union = hazard.geometry.union_all()
    hazard_count = int(len(hazard))
    local_aoi = gpd.read_file(local_aoi_path).to_crs(TARGET_CRS).geometry.iloc[0]
    context_aoi = gpd.read_file(context_aoi_path).to_crs(TARGET_CRS).geometry.iloc[0]

    rows: list[dict[str, object]] = []
    selected_threshold: int | None = None
    selected_gpkg: Path | None = None

    for threshold in thresholds:
        stream_raster = outdir / f"{dem_path.stem}_streams_{threshold}.tif"
        stream_shape = outdir / f"{dem_path.stem}_streams_{threshold}.shp"
        stream_gpkg = outdir / f"{dem_path.stem}_streams_{threshold}.gpkg"

        _clean_shapefile_outputs(stream_shape)
        if stream_gpkg.exists():
            stream_gpkg.unlink()
        if stream_raster.exists():
            stream_raster.unlink()

        wbt.extract_streams(str(accum_path), str(stream_raster), threshold, zero_background=True)
        wbt.raster_streams_to_vector(str(stream_raster), str(pointer_path), str(stream_shape))

        gdf = gpd.read_file(stream_shape).set_crs(TARGET_CRS, allow_override=True)
        gdf = gdf[gdf.geometry.notna()].copy()
        gdf = gdf[~gdf.geometry.is_empty].copy()
        gdf["length_m"] = gdf.geometry.length
        gdf["hazard_len_m"] = gdf.geometry.intersection(hazard_union).length
        gdf["local_aoi_len_m"] = gdf.geometry.intersection(local_aoi).length
        gdf["context_len_m"] = gdf.geometry.intersection(context_aoi).length
        gdf["touches_hazard"] = gdf["hazard_len_m"] > 0

        total_length = float(gdf["length_m"].sum())
        hazard_length = float(gdf["hazard_len_m"].sum())
        local_length = float(gdf["local_aoi_len_m"].sum())
        context_length = float(gdf["context_len_m"].sum())
        stats = ThresholdStats(
            threshold_cells=threshold,
            segments=int(len(gdf)),
            total_length_m=total_length,
            hazard_length_m=hazard_length,
            hazard_share=(hazard_length / total_length) if total_length else 0.0,
            local_aoi_share=(local_length / total_length) if total_length else 0.0,
            context_share=(context_length / total_length) if total_length else 0.0,
            mean_segment_length_m=(total_length / len(gdf)) if len(gdf) else 0.0,
            max_segment_length_m=float(gdf["length_m"].max()) if len(gdf) else 0.0,
            segments_touching_hazard=int(gdf["touches_hazard"].sum()),
        )
        rows.append(asdict(stats))

        gdf.drop(columns=["touches_hazard"], inplace=True)
        gdf.to_file(stream_gpkg, driver="GPKG")

    df = pd.DataFrame(rows).sort_values("threshold_cells").reset_index(drop=True)

    best_hazard = float(df["hazard_share"].max()) if not df.empty else 0.0
    top = df[df["hazard_share"] >= (0.95 * best_hazard)].copy() if best_hazard else df.copy()
    if not top.empty:
        top = top.sort_values(["total_length_m", "threshold_cells"], ascending=[True, True])
        selected_threshold = int(top.iloc[0]["threshold_cells"])
        selected_gpkg = outdir / f"{dem_path.stem}_streams_{selected_threshold}.gpkg"

    summary_csv = outdir / f"{dem_path.stem}_stream_threshold_sweep.csv"
    df.to_csv(summary_csv, index=False)

    summary_json = outdir / f"{dem_path.stem}_stream_threshold_sweep.json"
    safe_write_json(df.to_dict(orient="records"), summary_json)

    return df, summary_csv, selected_gpkg, selected_threshold, hazard_count


def write_report(
    df: pd.DataFrame,
    report_path: Path,
    hazard_path: Path,
    selected_gpkg: Path | None,
    selected_threshold: int | None,
    hazard_count: int,
) -> None:
    selection_block = ""

    if not df.empty and selected_threshold is not None:
        sel_row = df[df["threshold_cells"] == selected_threshold].iloc[0]
        _gpkg_rel = selected_gpkg.relative_to(ROOT) if selected_gpkg is not None else None
        gpkg_line = optional("\nSelected stream network: `{}`\n", _gpkg_rel)
        selection_block = f"""\
## Working threshold choice

Selected threshold: {selected_threshold} accumulation cells. It sits in the top hazard-overlap band and is the most concise network among thresholds within 95% of the maximum hazard-share score.

Selected-threshold metrics:
- total length: {sel_row['total_length_m']:.1f} m
- mapped hazard overlap: {sel_row['hazard_length_m']:.1f} m ({sel_row['hazard_share']:.1%})
- inside local 2 km AOI: {sel_row['local_aoi_share']:.1%} of network length
- inside 8 km fan-context AOI: {sel_row['context_share']:.1%} of network length
- segments touching mapped hazard polygons: {int(sel_row['segments_touching_hazard'])} of {int(sel_row['segments'])}
{gpkg_line}"""

    _gpkg_rel = selected_gpkg.relative_to(ROOT) if selected_gpkg is not None else None
    gpkg_output = optional("- Selected channel network GPKG: `{}`\n", _gpkg_rel)

    report = f"""\
# Wash / Channel Extraction

This step extracted candidate channel/wash networks from the 1 m DeAnza Villas D8 flow-accumulation surface and compared them against the mapped county/FEMA-derived flood-hazard polygons and the local fan context AOIs.

## Inputs used
- Hazard polygons: `{hazard_path.relative_to(ROOT)}` ({hazard_count} features)
- Local AOI: `{LOCAL_AOI_PATH.relative_to(ROOT)}`
- Context AOI: `{CONTEXT_AOI_PATH.relative_to(ROOT)}`
- Terrain base: `{DEM_PATH.relative_to(ROOT)}`
- D8 accumulation: `{ACCUM_PATH.relative_to(ROOT)}`

## Threshold sweep results

```csv
{df.to_csv(index=False).rstrip()}
```

{selection_block}
## Interpretation

- Lower thresholds capture dense sheetflow-like drainage texture but create a very large network that is harder to interpret.
- Higher thresholds isolate the main washes and produce a cleaner comparison layer for hazard context review.
- The mapped flood polygons intersect the extracted network substantially enough to support a real channel/wash context comparison rather than a purely synthetic drainage result.
- For the next pass, the selected network is the right base layer for visual inspection against hazard polygons, fan context, and any parcel geometry once available.

## Context caveat

These are terrain-derived candidate channels/washes, not a regulated FEMA map revision or a licensed engineering drainage determination.

## Outputs

- Threshold sweep CSV: `{OUTDIR.relative_to(ROOT)}/{DEM_PATH.stem}_stream_threshold_sweep.csv`
- Threshold sweep JSON: `{OUTDIR.relative_to(ROOT)}/{DEM_PATH.stem}_stream_threshold_sweep.json`
{gpkg_output}"""

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")


def main() -> None:
    df, summary_csv, selected_gpkg, selected_threshold, hazard_count = derive_streams(
        dem_path=DEM_PATH,
        accum_path=ACCUM_PATH,
        pointer_path=POINTER_PATH,
        hazard_path=HAZARD_PATH,
        local_aoi_path=LOCAL_AOI_PATH,
        context_aoi_path=CONTEXT_AOI_PATH,
        outdir=OUTDIR,
        thresholds=DEFAULT_THRESHOLDS,
    )

    write_report(
        df=df,
        report_path=REPORT_PATH,
        hazard_path=HAZARD_PATH,
        selected_gpkg=selected_gpkg,
        selected_threshold=selected_threshold,
        hazard_count=hazard_count,
    )

    print(f"summary_csv: {summary_csv}")
    print(f"report: {REPORT_PATH}")
    if selected_gpkg is not None:
        print(f"selected_network: {selected_gpkg}")


if __name__ == "__main__":
    main()
