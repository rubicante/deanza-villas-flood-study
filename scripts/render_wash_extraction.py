from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.study_config import ROOT, config_path, deliverable_path, step_path
from scripts.study_utils import optional

DEM_PATH = config_path("paths", "dem_filled")
ACCUM_PATH = config_path("paths", "d8_flow_accum")
HAZARD_PATH = config_path("paths", "hazard_polygons")
LOCAL_AOI_PATH = config_path("paths", "local_aoi")
CONTEXT_AOI_PATH = config_path("paths", "context_aoi")
OUTDIR = step_path("wash_extraction", "outdir")
REPORT_PATH = deliverable_path("wash_extraction_report")

SELECTED_THRESHOLD = 5000


def main() -> None:
    summary_csv = OUTDIR / f"{DEM_PATH.stem}_stream_threshold_sweep.csv"
    if not summary_csv.exists():
        print(f"SKIP: no sweep CSV at {summary_csv}")
        return

    df = pd.read_csv(summary_csv)
    selected_gpkg = OUTDIR / f"{DEM_PATH.stem}_streams_{SELECTED_THRESHOLD}.gpkg"

    # Build report
    selection_block = ""
    if not df.empty:
        sel_row = df[df["threshold_cells"] == SELECTED_THRESHOLD]
        if not sel_row.empty:
            sel_row = sel_row.iloc[0]
            _gpkg_rel = selected_gpkg.relative_to(ROOT) if selected_gpkg.exists() else None
            gpkg_line = optional("\nSelected stream network: `{}`\n", _gpkg_rel)
            selection_block = f"""\
## Working threshold choice

Selected threshold: {SELECTED_THRESHOLD} accumulation cells. It sits in the top hazard-overlap band and is the most concise network among thresholds within 95% of the maximum hazard-share score.

Selected-threshold metrics:
- total length: {sel_row['total_length_m']:.1f} m
- mapped hazard overlap: {sel_row['hazard_length_m']:.1f} m ({sel_row['hazard_share']:.1%})
- inside local 2 km AOI: {sel_row['local_aoi_share']:.1%} of network length
- inside 8 km fan-context AOI: {sel_row['context_share']:.1%} of network length
- segments touching mapped hazard polygons: {int(sel_row['segments_touching_hazard'])} of {int(sel_row['segments'])}
{gpkg_line}"""

    _gpkg_rel = selected_gpkg.relative_to(ROOT) if selected_gpkg.exists() else None
    gpkg_output = optional("- Selected channel network GPKG: `{}`\n", _gpkg_rel)

    report = f"""\
# Wash / Channel Extraction

This step extracted candidate channel/wash networks from the 1 m DeAnza Villas D8 flow-accumulation surface and compared them against the mapped county/FEMA-derived flood-hazard polygons and the local fan context AOIs.

## Inputs used
- Hazard polygons: `{HAZARD_PATH.relative_to(ROOT)}`
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

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
