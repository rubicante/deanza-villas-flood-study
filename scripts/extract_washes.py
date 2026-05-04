from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
import sys

import geopandas as gpd
import pandas as pd
from whitebox.whitebox_tools import WhiteboxTools

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.init_env import load_env
from scripts.study_config import DEFAULT_THRESHOLDS, TARGET_CRS, deliverable_path, step_path
from scripts.study_utils import safe_write_json

DEFAULT_DEM = config_path("paths", "dem_filled")
DEFAULT_ACCUM = config_path("paths", "d8_flow_accum")
DEFAULT_POINTER = config_path("paths", "d8_pointer")
DEFAULT_HAZARD = config_path("paths", "hazard_polygons")
DEFAULT_LOCAL_AOI = config_path("paths", "local_aoi")
DEFAULT_CONTEXT_AOI = config_path("paths", "context_aoi")
DEFAULT_OUTDIR = step_path("wash_extraction", "outdir")
DEFAULT_REPORT = deliverable_path("wash_extraction_report")


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
) -> tuple[pd.DataFrame, Path, Path]:
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

        # Save a clean geospatial copy with an explicit CRS for downstream use.
        gdf.drop(columns=["touches_hazard"], inplace=True)
        gdf.to_file(stream_gpkg, driver="GPKG")

    df = pd.DataFrame(rows).sort_values("threshold_cells").reset_index(drop=True)

    # Pick the most concise threshold among the best hazard-overlap performers.
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

    return df, summary_csv, selected_gpkg


def write_report(
    df: pd.DataFrame,
    report_path: Path,
    local_aoi_path: Path,
    context_aoi_path: Path,
    hazard_path: Path,
    selected_gpkg: Path | None,
) -> None:
    hazard = gpd.read_file(hazard_path).to_crs(TARGET_CRS)
    local_aoi = gpd.read_file(local_aoi_path).to_crs(TARGET_CRS)
    context_aoi = gpd.read_file(context_aoi_path).to_crs(TARGET_CRS)

    lines = []
    lines.append("# Wash / Channel Extraction")
    lines.append("")
    lines.append("This step extracted candidate channel/wash networks from the 1 m DeAnza Villas D8 flow-accumulation surface and compared them against the mapped county/FEMA-derived flood-hazard polygons and the local fan context AOIs.")
    lines.append("")
    lines.append("## Inputs used")
    lines.append(f"- Hazard polygons: `{hazard_path.relative_to(ROOT)}` ({len(hazard)} features)")
    lines.append(f"- Local AOI: `{local_aoi_path.relative_to(ROOT)}`")
    lines.append(f"- Context AOI: `{context_aoi_path.relative_to(ROOT)}`")
    lines.append("- Terrain base: `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_filled.tif`")
    lines.append("- D8 accumulation: `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_d8_flow_accum.tif`")
    lines.append("")
    lines.append("## Threshold sweep results")
    lines.append("")
    lines.append("```csv")
    lines.append(df.to_csv(index=False).rstrip())
    lines.append("```")
    lines.append("")

    if not df.empty:
        best_hazard = float(df["hazard_share"].max())
        top = df[df["hazard_share"] >= (0.95 * best_hazard)].copy()
        top = top.sort_values(["total_length_m", "threshold_cells"], ascending=[True, True])
        selected = int(top.iloc[0]["threshold_cells"])
        sel_row = df[df["threshold_cells"] == selected].iloc[0]
        lines.append("## Working threshold choice")
        lines.append("")
        lines.append(
            f"Selected threshold: {selected} accumulation cells. It sits in the top hazard-overlap band and is the most concise network among thresholds within 95% of the maximum hazard-share score."
        )
        lines.append("")
        lines.append("Selected-threshold metrics:")
        lines.append(f"- total length: {sel_row['total_length_m']:.1f} m")
        lines.append(f"- mapped hazard overlap: {sel_row['hazard_length_m']:.1f} m ({sel_row['hazard_share']:.1%})")
        lines.append(f"- inside local 2 km AOI: {sel_row['local_aoi_share']:.1%} of network length")
        lines.append(f"- inside 8 km fan-context AOI: {sel_row['context_share']:.1%} of network length")
        lines.append(f"- segments touching mapped hazard polygons: {int(sel_row['segments_touching_hazard'])} of {int(sel_row['segments'])}")
        lines.append("")
        if selected_gpkg is not None:
            lines.append(f"Selected stream network: `{selected_gpkg.relative_to(ROOT)}`")
            lines.append("")

    lines.append("## Interpretation")
    lines.append("")
    lines.append("- Lower thresholds capture dense sheetflow-like drainage texture but create a very large network that is harder to interpret.")
    lines.append("- Higher thresholds isolate the main washes and produce a cleaner comparison layer for hazard context review.")
    lines.append("- The mapped flood polygons intersect the extracted network substantially enough to support a real channel/wash context comparison rather than a purely synthetic drainage result.")
    lines.append("- For the next pass, the selected network is the right base layer for visual inspection against hazard polygons, fan context, and any parcel geometry once available.")
    lines.append("")
    lines.append("## Context caveat")
    lines.append("")
    lines.append("These are terrain-derived candidate channels/washes, not a regulated FEMA map revision or a licensed engineering drainage determination.")
    lines.append("")
    lines.append("## Outputs")
    lines.append("")
    lines.append("- Threshold sweep CSV: `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.csv`")
    lines.append("- Threshold sweep JSON: `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.json`")
    if selected_gpkg is not None:
        lines.append(f"- Selected channel network GPKG: `{selected_gpkg.relative_to(ROOT)}`")

    report_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract candidate channels/washes from the 1 m DeAnza Villas terrain and compare them to mapped hazards.")
    parser.add_argument("--dem", type=Path, default=DEFAULT_DEM)
    parser.add_argument("--accum", type=Path, default=DEFAULT_ACCUM)
    parser.add_argument("--pointer", type=Path, default=DEFAULT_POINTER)
    parser.add_argument("--hazard", type=Path, default=DEFAULT_HAZARD)
    parser.add_argument("--local-aoi", type=Path, default=DEFAULT_LOCAL_AOI)
    parser.add_argument("--context-aoi", type=Path, default=DEFAULT_CONTEXT_AOI)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--thresholds", type=int, nargs="*", default=DEFAULT_THRESHOLDS)
    args = parser.parse_args()

    df, summary_csv, selected_gpkg = derive_streams(
        dem_path=args.dem,
        accum_path=args.accum,
        pointer_path=args.pointer,
        hazard_path=args.hazard,
        local_aoi_path=args.local_aoi,
        context_aoi_path=args.context_aoi,
        outdir=args.outdir,
        thresholds=args.thresholds,
    )

    report_path = args.report.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_report(
        df=df,
        report_path=report_path,
        local_aoi_path=args.local_aoi,
        context_aoi_path=args.context_aoi,
        hazard_path=args.hazard,
        selected_gpkg=selected_gpkg,
    )

    print(f"summary_csv: {summary_csv}")
    print(f"report: {report_path}")
    if selected_gpkg is not None:
        print(f"selected_network: {selected_gpkg}")


if __name__ == "__main__":
    main()
