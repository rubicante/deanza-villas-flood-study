# Borrego Springs Flood Study Final Report Plan

Status: drafted
Date: 2026-05-02

This plan converts the completed phase 1–4 analysis into one canonical final report with embedded static figures and links to the existing interactive HTML maps.

## Working thesis

De Anza Villas is materially exposed to active alluvial-fan / concentrated-flow flood hazard on the Borrego Springs valley floor. The report will stay strictly inside the evidence produced by the project:
- official flood-context layers and documents
- 1 m terrain reconstruction and wash extraction
- authoritative parcel overlay
- fan-activity synthesis
- OPERA satellite validation

The report will not invent calibrated flood depths, regulatory determinations, or new hydrodynamic modeling results.

## Recommended final deliverable

One canonical markdown report, with:
- an executive summary at the top
- 4–6 static figures embedded in the narrative
- a source/evidence appendix
- links to the existing interactive HTML maps for deeper inspection

Suggested file:
- `outputs/reports/final_report.md`

Suggested figure directory:
- `outputs/figures/final_report/`

## Graphics strategy

Use figures that are common in alluvial-fan flood reports and that we can support with our actual outputs:
1. Study-area / regulatory-context map
2. Terrain + drainage concentration map
3. Parcel-scale overlay map
4. Quantitative comparison chart
5. Satellite validation figure
6. Optional threshold-selection chart in the appendix

Preferred principle:
- figures should prove one thing each
- maps should be clean, sparse, and legible
- no unsupported synthetic inundation depth maps
- no profile/cross-section centerpiece, because FEMA notes profiles have limited utility in true 2-D / alluvial-fan settings

## Step-by-step plan

### Step 1: Lock report scope and message
Objective: write the exact conclusion framing before drafting prose.

Decisions to freeze:
- canonical audience: private due-diligence, but polished enough to share
- tone: direct, rigorous, non-alarmist but explicit
- conclusion style: explicit if evidence supports material exposure
- structure: main report plus appendix/source inventory, not multiple competing final reports

Output for this step:
- one paragraph thesis
- one short “what this report is / is not” statement
- one bullet list of key findings and practical implications

### Step 2: Define the final figure list
Objective: decide exactly which visuals will be embedded.

Final figure set and source data:

- Figure 1 — Study area and flood-context overview
  - Purpose: orient the reader and show the parcel in its mapped hazard setting.
  - Layers: parcel boundary, parcel polygons, local AOI, context AOI, FEMA hazard polygons.
  - Primary source files:
    - `data/vectors/deanza_villas_complex_boundary.geojson`
    - `data/vectors/deanza_villas_parcel_polygons.geojson`
    - `data/vectors/deanza_villas_2km_aoi.geojson`
    - `data/vectors/borrego_valley_context_8km_aoi.geojson`
    - `data/raw/fema/oes_know_your_hazards_flooding_borrego.geojson`

- Figure 2 — Terrain and extracted drainage fabric
  - Purpose: show the terrain structure and concentrated-flow texture driving the interpretation.
  - Layers: hillshade or slope background from the 1 m DEM, selected 5000-cell channel network, FEMA hazard polygons.
  - Primary source files:
    - `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_filled.tif`
    - `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_slope_degrees.tif`
    - `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg`
    - `data/raw/fema/oes_know_your_hazards_flooding_borrego.geojson`

- Figure 3 — Parcel-scale channel/hazard overlap
  - Purpose: show exactly how the selected network intersects the authoritative parcel geometry.
  - Layers: dissolved boundary, parcel polygons, selected network, highlighted parcel-crossing segments, FEMA hazard polygons.
  - Primary source files:
    - `data/vectors/deanza_villas_complex_boundary.geojson`
    - `data/vectors/deanza_villas_parcel_polygons.geojson`
    - `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg`
    - `data/processed/terrain/deanza_villas_2km_1m/parcels/deanza_villas_2km_1m_dem_filled_streams_5000_in_parcel.gpkg`
    - `data/raw/fema/oes_know_your_hazards_flooding_borrego.geojson`

- Figure 4 — Quantitative terrain comparison
  - Purpose: compress the terrain evidence into a simple parcel vs local AOI vs context comparison.
  - Variables: stream density, relief, slope, roughness.
  - Primary source file:
    - `data/processed/terrain/deanza_villas_2km_1m/fan_synthesis/phase3_fan_synthesis_stats.csv`

- Figure 5 — Satellite validation
  - Purpose: show the strongest available positive wetting evidence without overclaiming.
  - Primary scene:
    - HLS selected scene date `2023-08-22`
    - browse image `data/processed/terrain/deanza_villas_2km_1m/validation_phase4/downloads/OPERA_L3_DSWx-HLS_T11SNS_20230822T182232Z_20230824T134308Z_L8_30_v1.0_BROWSE.png`
  - Companion evidence:
    - `data/processed/terrain/deanza_villas_2km_1m/validation_phase4/phase4_satellite_validation_selected.json`
  - Recommended presentation: a two-part figure with the browse image and a compact summary panel showing local/parcel water counts.

- Figure 6 — Threshold justification (appendix or methods)
  - Purpose: document why the 5000-cell stream threshold was chosen.
  - Variables: threshold vs hazard share, total length, segments, and local/context coverage.
  - Primary source file:
    - `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.csv`

Production method decision:
- Use direct Python export for Figures 1–4 where practical, so the final report has clean, reproducible PNGs rather than screenshots.
- Use the OPERA browse PNG directly for Figure 5, with a small annotation panel added in Python.
- Use a simple charting library for Figure 4 and Figure 6; keep the styling sparse and publication-clean.
- Reserve the existing HTML maps for linked interactivity, not for embedding as the main graphics.

### Step 3: Decide production method for each figure
Objective: choose the most reliable way to generate clean static graphics.

Figure-by-figure production plan:

- Figure 1 — `outputs/figures/final_report/figure1_context_overview.png`
  - Build a static map in Python with geopandas + matplotlib.
  - Use parcel boundary, parcel polygons, local AOI, context AOI, and FEMA hazard polygons.
  - Keep the basemap minimal or omit it if it reduces legibility.

- Figure 2 — `outputs/figures/final_report/figure2_terrain_drainage.png`
  - Build a static map in Python with rasterio + matplotlib.
  - Use hillshade derived from the filled DEM or a slope raster as the background.
  - Overlay the selected channel network and FEMA hazard polygons.
  - Add a north arrow, scale bar, and clean legend.

- Figure 3 — `outputs/figures/final_report/figure3_parcel_overlap.png`
  - Build a static parcel-scale map in Python with geopandas + matplotlib.
  - Emphasize the dissolved boundary and the parcel-crossing stream segments.
  - Use the parcel polygons as lighter context and the selected parcel-only stream layer as a highlight.

- Figure 4 — `outputs/figures/final_report/figure4_terrain_comparison.png`
  - Build a compact multi-panel chart in Python with matplotlib.
  - Preferred layout: four small panels or one grouped dot/bar chart.
  - Variables: relief, slope, roughness, stream density.
  - Compare parcel vs local AOI vs context AOI.

- Figure 5 — `outputs/figures/final_report/figure5_satellite_validation.png`
  - Use the selected OPERA browse PNG as the visual base.
  - Add a right-side or bottom summary panel in matplotlib with the key counts:
    - HLS date 2023-08-22
    - local water pixels = 12
    - parcel water pixels = 1
    - overall water pixels = 73,516
  - If georeferenced annotation is awkward, keep the graphic simple and caption the limitations clearly.

- Figure 6 — `outputs/figures/final_report/figure6_threshold_justification.png`
  - Build a small line or scatter chart from the threshold sweep CSV.
  - Show threshold vs hazard share and threshold vs network size/segments.
  - This can live in the methods section or appendix.

Implementation posture:
- prefer direct plot generation over screenshotting whenever we have the underlying layers
- only use screenshots as a fallback for the HTML maps if static export becomes brittle
- keep styling sparse and publication-clean so the graphics read as evidence, not decoration
- make sure every image is reproducible from the checked-in data and scripts

### Step 4: Draft the report outline
Objective: lock the section structure before writing prose.

Recommended outline:
1. Title
2. Executive summary
3. Study area and question
4. Official flood-context evidence
5. Terrain reconstruction and wash extraction
6. Parcel-scale overlay
7. Fan-activity synthesis
8. Satellite validation
9. Bottom-line assessment and recommendations
10. Caveats and limits
11. Appendix: figures, maps, source inventory

### Step 5: Write the report around the evidence chain
Objective: draft each section so every major claim is tied to a computed result or source layer.

Section logic:
- official context: FEMA / County / Boyle / DRI
- terrain: slope, relief, roughness, extracted washes
- parcel overlay: exact dissolved boundary and parcel polygons
- synthesis: active-fan interpretation from our own analysis
- satellite: positive wetting evidence and the meaning of non-detections

### Step 6: Tighten the recommendations
Objective: keep recommendations rigorous and bounded by the analysis.

Recommendations should be practical, not overreaching. Likely categories:
- treat the parcel as materially flood-exposed in due diligence
- review insurance / lender / permitting implications carefully
- if formal design or permitting is needed, hand off to a licensed professional for site-specific work
- do not rely on apparent channel stability as proof of future stability

### Step 7: Verify figure-label consistency and source traceability
Objective: make sure the report is defensible.

Checklist:
- every figure has a caption that states the analytical point, not just the contents
- every map path is correct
- every numeric claim matches a CSV or report output
- no figure implies a regulatory determination we did not produce
- all interactive HTML maps are linked as supporting detail

### Step 8: Final polish and canonicalization
Objective: remove ambiguity and competing artifacts.

Finish by ensuring:
- one primary final report path
- one figure set
- one appendix/source inventory
- older phase reports remain as supporting evidence, not alternate final narratives

## Immediate next action

Begin Step 1 now by drafting the exact thesis paragraph and the report’s opening summary language.

### Step 1 draft: thesis and opening summary

Thesis paragraph draft:

De Anza Villas sits on an active Borrego Springs alluvial-fan surface where the terrain, mapped hazard context, parcel overlay, and satellite evidence all point to meaningful concentrated-flow flood exposure. The 1 m terrain reconstruction shows a dense drainage fabric and substantial local relief; the selected extracted wash network overlaps the mapped flood-hazard polygons; the authoritative parcel boundary intercepts that network; the fan-activity synthesis is consistent with active-fan behavior rather than stable channel confinement; and OPERA surface-water detections provide positive wetting evidence in the study area. Taken together, the evidence supports a serious due-diligence concern, not a benign or marginal flood setting.

Opening summary draft:

This report reconstructs and tests the flood-risk logic relevant to De Anza Villas using the best public evidence available for Borrego Springs alluvial-fan terrain. It brings together official flood-context materials, a 1 m lidar-derived terrain analysis, an exact parcel overlay, fan-activity interpretation, and satellite validation. The conclusion is bounded by the data produced here: the parcel is materially exposed to concentrated-flow / alluvial-fan flood hazard, and apparent channel forms should not be treated as stable or protective.
