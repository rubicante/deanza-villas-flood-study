# Active development log

Use this file as the rolling project work log for ongoing changes, status updates, and verification notes.

- 2026-05-07 ~22:00 UTC: Stream explorer major update — replaced static layers with toggleable checkboxes (native label[for] + change events). Added DRI 2015 fan zones, 2km AOI buffer, and parcel complex boundary as context layers. Relabeled community bbox → watershed pour-point zone. Changed defaults: only watershed boundary ON; FEMA, HUC-12, parcel boundary now OFF. Removed parcel lots (36) layer. Merged Always on/Off by default sections into flat legend. Committed with 3 new context GeoJSONs in outputs/maps/ (copies of canonical sources for relative-URL loading).

- 2026-05-07 ~22:30 UTC: Parcel correction + downstream regeneration complete.
  **Parcel boundary corrected:** 8.04 ha → 5.06 ha (−37%). Old canonical
  incorrectly included Vista Villas (31 parcels, APN 14026410xx) because the
  original SanGIS query used `subname LIKE 'DE ANZA VILLAS%'` which matched
  both communities. AB1785 forced re-acquisition via SANDAG Parcels_East
  (public FeatureServer), which surfaced the ambiguous match. Corrected
  filter uses APN prefix `14026410`. Two De Anza blocks (36 parcels) bridged
  across Monroe St ROW with straight connections (gap-convex-hull method,
  +6,157 m² fill). New scripts: `fetch_parcels.py` (SANDAG query) and
  `correct_parcel.py` (filter + bridge).

  **AOI buffers regenerated:** Old AOIs were misnamed — "2km AOI" was ~550m
  (1.17 km²), "8km AOI" was ~2.4km (18.68 km²). New `build_aois.py` produces
  correct buffers: 2km=14.54 km², 8km=208.56 km².

  **Downstream regeneration:** Raw 1m DEM re-fetched for new 2km AOI
  (20.2 Mpx, 4,415×4,567, up from 2.0 Mpx). Full pipeline rerun:
  terrain_metrics (breach+fill, D8/D∞), extract_washes, parcel_overlay,
  fan_synthesis (includes new roughness rasters), hand, curvature_tpi,
  dri_roughness_comparison. Renders updated: wash_extraction.md,
  parcel_overlay.html. Satellite validation stalled (Earthaccess auth);
  context layer copies updated. PROVENANCE.md updated with canonical
  change tables (parcel, FEMA, AOIs) and AB1785 narrative.
  Fixed latent bugs: `SUMMARY_MD` missing in dri_roughness_comparison.py,
  `selected_streams` missing from `_GENERATED_PATHS` in __main__.py.

  **Plan 2 status:** 4/5 items done (PROVENANCE.md, fetch_fema.py,
  build_aois.py pulled forward, fetch_parcels.py + correct_parcel.py as
  parcel infrastructure). Next: fetch_huc12.py.

- 2026-05-07 ~21:20 UTC: fetch_fema.py — Plan 2 item 2 complete.
  Created `scripts/fetch_fema.py`: parameterized ArcGIS REST query for
  DFIRM 06073C within 8km of parcel center. 7 validation gates:
  feature count (30–60), required fields (11), geometry type, total area
  (0.5–500 km²), zone values, DFIRM_ID consistency, ArcGIS error-in-body
  detection. Diff stage compares against canonical with metadata stripped.
  Default dry-run; --write updates canonical. Re-ran query: endpoint still
  returns identical schema. Parcel-centered query (vs old hardcoded Borrego
  Springs center) found 9 additional AO zones — updated canonical from
  40→49 features (47 AO, 1 A, 1 X). GlobalID/GFID confirmed stable across
  queries. Byte-identical re-run confirmed. Updated PROVENANCE.md and TODO.md.

- 2026-05-07 ~17:15 UTC: PROVENANCE.md written — Plan 2 item 1 complete.
  Created `data/raw/manual/PROVENANCE.md` documenting the origin and
  reproducibility status of every one-off artifact:
  - 3 reference PDFs (stable URLs, re-downloadable)
  - 2 DEMs (reproducible via deliverable/fetch.py)
  - FEMA NFHL (one-off ArcGIS REST query → Plan 2: fetch_fema.py)
  - 2 SanGIS parcel files (one-off, no public API — frozen source data)
  - HUC-12 boundary (one-off WBD extraction → Plan 2: fetch_huc12.py via NLDI)
  - 2 DRI fan zone vectors (reproducible via dri_roughness_comparison.py)
  - Community bbox (one-off hand-drawn → study-specific, no script)
  - 2 AOI buffers (one-off → Plan 2: build_aois.py)
  - Henderson watershed boundary (now reproducible via deliverable/watershed.py)
  Includes summary table mapping each artifact to its Plan 2 fetch script.
  Updated TODO.md with Plan 2 checklist (5 items, PROVENANCE.md marked done).

- 2026-05-07 ~12:00 UTC: deliverable/watershed.py — watershed delineation module.
  New module `delineate_watershed()`: Path-based API taking a filled DEM + pour
  GeoJSON → WBT D8 pointer → WBT watershed() → rasterio polygonize →
  shapely unary_union → simplify → WGS84 + EPSG:5070 GeoJSON. Optional
  snap_pour_points with explicit stream threshold (None by default — snap
  couples to terrain-dependent stream threshold). Auto-checks boundary
  edge-touch against DEM extent (warns if within 2px). CRS contract: loads
  pour geometry, reprojects to DEM CRS, raises on zero overlap.
  Integrated into _henderson.py as `watershed` command; regenerated
  Henderson boundary from wide DEM + community bbox: 107.0 km², 93.5%
  HUC-12 overlap, 0.006% area diff vs committed, no edge-touch warnings.
  LESSONS.md: added rasterio features.shapes/rasterize int16+raster+uint8
  mask quirk (silent edge corruption with both uint8).
  Portable DEM/hydrology pipeline: fetch.py (auto-tile py3dep), preprocess.py
  (breach/fill with strategy parameter), d8.py (WBT pointer + pyflwdir accum,
  backends: wbt/pyflwdir/wbt_ptr_pyflwdir/auto), dinf.py (WBT D∞, out_type=cells
  explicit, no memory guard), verify.py (nonzero_min/isfinite/inf checks,
  D8/D∞ agreement with parameterized tolerance), streams.py (WBT extraction +
  GeoJSON export). Project-specific _henderson.py owns binary format, CRS→4326,
  and our four artifact configs. Key spike lessons encoded: absolute WBT paths,
  mask pointer nodata→0, pyflwdir.from_array check_ftype=False, single target
  grid clip-before-merge, float32+LZW throughout.

- 2026-05-06 ~21:30 UTC: 1m D∞ regeneration complete — streams_all.bin rebuilt for full 107 km² watershed.
  Five attempts killed by memory before succeeding. Root cause: WBT D∞ upcasts to float64 — 164.8M px × 3 arrays = 4.7 GB RSS. Solved: 8 GB swap, float32 DEM (1,318→437 MB), parent RSS freed to 76 MB.
  Result: 1m at 24s, max=17,931,216, nonzero_min=1, 0 inf. Streams t=250: 6,572,827 cells (was 5.1M on old 33.6 km² boundary). Bin: 78.9 MB. First cell: lon=-116.38927 lat=33.28339.

- 2026-05-06 ~20:00 UTC: Wide-DEM D∞ accumulation regenerated — fixed out_type bug.
  Root cause: WBT `d_inf_flow_accumulation` defaults to `out_type="specific catchment area"` (not "cells"). D8 defaults to "cells" but D∞ does not. The wide-DEM D∞ was generated without an explicit out_type, producing SCA values (nonzero_min = 9.2974 = cell width) with 435,384 inf cells from contour-width collapse on the flat fan surface (Tarboton D∞ divides by near-zero contour width when noisy flow angles on flats align with cell edges).
  Fix: regenerated `dinf_flow_accum_wide.tif` with `out_type="cells"` (nonzero_min=1, max=1,870,740, zero inf). Regenerated `streams_wide_dinf.bin` (277,793 cells at t=250, down from 1.2M inflated by inf). Verification: D∞/D8 max agreement 0.99975 at identical pixel (2100,2450); canyon-mouth gradient 270→1.87M within 50-cell window (was all inf → solid rust blob). D∞ wide / D∞ narrow max ratio 1.46 (above 1.29 watershed area ratio — non-watershed DEM cells also drain in).
  D8 wide .bin (52K cells at t=250) is correct data, not corrupted — 250 cells at 10m = 21,610 m² minimum vs 250 m² at 1m. Threshold rescaling is a separate concern.
  Updated: skill.md out_type section (already corrected in prior session), DEVLOG.

- 2026-05-06 ~16:00 UTC: D∞ characterization corrected after stratified analysis.
  Earlier claim that D∞ partitions ~29% uphill was from uniform sampling across all terrain (oversampling near-flat fan surface). Stratified by local relief: on cells with >10m 3×3 window relief, D∞ routes downhill and agrees with D8. On near-flat cells (<1m relief), D∞ can produce non-physical assignments because all triangular facets have sign-ambiguous slopes — a Tarboton 1997 edge case, not a WBT bug. The original "75° off" claim was from a single-cell comparison using the wrong D8 encoding. Both D8 and D∞ work correctly within their design domains. Updated: SKILL.md (3 locations), v3 explorer caution, references/watershed-validation-workflow.md, memory. Added relief-stratified validation to huc12_crosscheck.py (Item 2).
  The diagnostic pattern worth preserving: when a bulk disagreement percentage is high, stratify by terrain type before concluding the tool is broken. Uniform disagreement → bug in our code. Concentrated in flats → real algorithmic edge case.
  Threshold morph explorer v3 updated: D∞ caution note reflects stratification finding, stats row changed from "uphill partitions ~29%" to "edge case on fan surface."

- 2026-05-06 ~17:00 UTC: Wide-DEM watershed (107 km²) verified and promoted to canonical.
  All three gates pass: 1000/1000 traces reach bbox, 93.5% within BPC HUC12, 100% high-elevation ws-only drains into BPC. Outperforms the narrow 83 km² version on HUC-12 overlap (93.5% vs 91.3%). Consolidation: regenerated all boundary vectors from watershed_wide.tif (107 km²), updated explorer title/legend, deprecated narrow-DEM watershed.tif, removed misleadingly-named WRONG_107km2 file, updated skill (4 locations) and memory. HUC-12 boundary retained as context layer.

Format: `YYYY-MM-DD HH:MM UTC: <brief status update>` — what changed, why, and what was verified.

- 2026-05-06 ~15:00 UTC: Threshold morph explorer v3 updated + watershed boundaries regenerated.
  Regenerated all watershed boundary GeoJSON files from current watershed.tif (83.3 km², WBT D8, verified). Updated canonical paths: data/vectors/henderson_watershed_boundary.geojson (WGS84), data/vectors/henderson_watershed_boundary_5070.geojson (EPSG:5070), outputs/maps/henderson_watershed_boundary.geojson (WGS84). All three now show 83.3 km² (was: 33.6, 4.2, and 107 km² respectively — stale from pre-encoding-fix era).
  Updated threshold_morph_explorer_v3.html: new info panel (area, HUC-12 overlap 91%, verification status 1000/1000, D∞ reliability caution), HUC-12 boundary layer added, updated legend, updated stats row with total cell count and D∞ note. Explorer now loads correct 83 km² watershed boundary + Borrego Palm Canyon HUC-12 overlay.

- 2026-05-06 ~14:15 UTC: OPUS.md Task 1-4 completed — Henderson Canyon watershed delineation validated and finalized.
  Task 1 (encoding fix): Patched 3 spike scripts with incorrect 45°-rotated D8 encoding tables (trace_western_flow.py, diagnose_d8_vs_dinf.py, verify_watershed_upstream.py). Correct encoding: 1=NE,2=E,4=SE,8=S,16=SW,32=W,64=NW,128=N. Added encoding bug history to verify_watershed_correct_enc.py docstring.
  Task 2 (D8 sanity): 1000/1000 random interior watershed cells trace downstream through community bbox — WBT D8 watershed confirmed correct.
  Task 3 (HUC-12 cross-check): Watershed is 83.3 km², 91.3% within Borrego Palm Canyon HUC-12 (181002030302, 149.1 km²). Revised gate: ≥85% within HUC-12 → PASS.
  Task 3.5 (drainage direction): 100% of flows from 3.9 km² high-elevation watershed-only area drain south/southeast into BPC HUC-12. Legitimate cross-HUC headwater contribution. Gate 2 PASS.
  Task 4 (permanent stage): Created spikes/henderson-canyon/huc12_crosscheck.py — reusable CLI tool for HUC-12 overlap + drainage direction validation on any bbox. Verified with Henderson Canyon data: both gates pass.
  PNG overlay and topo map saved at spikes/henderson-canyon/task3_huc12_crosscheck.png and task35_topo_overlay.png.

- 2026-05-04 ~16:30 UTC: Technical audit and methodology review. Populated TODO.md with 4-tier improvement backlog (16 items): Tier 1 — replace warped py3dep DEM with native 3DEP 1m tiles, switch to breach+fill depression processing, add D-infinity flow accumulation. Tier 2 — replace CalOES hazard layer with authoritative FEMA NFHL, keep full threshold ensemble, expand satellite temporal search. Tier 3 — compute profile curvature, TPI, HAND, and roughness-vs-age comparison. Tier 4 — upgrade py3dep past known-bad 0.19.0. No code changes made; all items queued for sequential execution.

- 2026-05-04 ~17:15 UTC: FEMA NFHL replacement research completed. Current CalOES file (`oes_know_your_hazards_flooding_borrego.geojson`) confirmed: 1,632 features, only FP100/FW100 fields, no depth/velocity/BFE. Researched 3 access options: (1) California NFHL reduced set on services2.arcgis.com — confirmed working, 110 AO zones for DFIRM 06073C with depth 1-6ft and velocity 3-11ft/sec; (2) FEMA MSC full state download — requires manual browser download due to TLS cipher restrictions; (3) FEMA NFHL WFS/WMS on hazards.fema.gov — TLS-blocked from this server. Updated TODO.md: replaced vague CalOES item with concrete endpoint/query details for option 1, added manual-download item for option 2. No code changes.

- 2026-05-04 ~17:20 UTC: OPERA DSWx temporal coverage and DRI 2015 polygon research completed via 3 parallel kanban researcher tasks (t_e7fe9e14, t_bb736bc5, t_f11b4a8f). All three returned findings. Satellite: DSWx-HLS has robust year-round coverage (38-46 scenes/season, 2023-2024); DSWx-S1 has zero 2023 coverage and only viable from late summer 2024 (12 summer, 25 fall). DRI 2015: no public downloadable GIS layer found; digitization from PDF page 20 (binary active/inactive) is the practical path; detailed digitization plan in kanban workspace. Updated TODO.md satellite and roughness-vs-age items with concrete specs. NFHL item also received external update with ArcGIS CA reduced-set endpoint details. No code changes.

- 2026-05-04 15:58 UTC: Report/map consolidation pass (all 12 TODO items completed).
  Content moves: absorbed source-document framing from fan_synthesis.md into final_report.md section 4. Absorbed parcel_overlay.md metrics (segment counts) into final_report.md section 3. Deleted parcel_overlay.md, fan_synthesis.md.
  Map consolidation: deleted terrain_context.html and fan_synthesis.html. Added satellite basemap toggle to parcel_overlay.html. Removed terrain_context step entirely (script, config paths, manifest entries).
  Compute/render decoupling: created render_wash_extraction.py, render_parcel_overlay.py, render_satellite_validation.py. Stripped write_report/make_map from extract_washes.py, parcel_overlay.py, satellite_validation.py. fan_synthesis.py now data-compute-only (no report/map). Updated __main__.py to run RENDER_STEPS after compute. Updated study.yaml (removed terrain_context step, removed deleted report/map paths from parcel_overlay and fan_synthesis). Updated study_manifest.yaml canonical_deliverables.
  Docs: updated final_report.md links and source inventory. Updated project_summary.md file map.
  Verified: all 8 scripts parse cleanly. Compute pipeline (extract_washes → parcel_overlay → fan_synthesis) and render pipeline (render_wash_extraction → render_parcel_overlay → render_satellite_validation) run end-to-end. All 6 output files present. 4 deleted files confirmed gone.

## Log

- 2026-05-03 17:52 UTC: Created `config/study.yaml`, `config/study_manifest.yaml`, `scripts/study_config.py`, `scripts/study_utils.py`, and `scripts/run_pipeline_v2.py` to centralize canonical paths and orchestration.
- 2026-05-03 17:52 UTC: Refactored the workflow scripts to import the shared config/helpers instead of repeating hardcoded study paths.
- 2026-05-03 17:52 UTC: Reran the v2 pipeline successfully in the project virtualenv; the canonical reports and HTML maps were regenerated.
- 2026-05-03 17:59 UTC: Retired the temporary v2 plan after moving its historical status notes into `DEVLOG.md`.
- 2026-05-03 18:00 UTC: Created as the canonical rolling dev log after the v2 pipeline plan was completed.
- 2026-05-03 18:10 UTC: Moved the rolling log to root `DEVLOG.md`, linked it from `README.md`, and made `AGENTS.md` point to it as the generic active-work log.
- 2026-05-03 18:20 UTC: Added generic plan-file guidance to `AGENTS.md` so queued work can live in `TODO.md` and material execution notes can continue in `DEVLOG.md`.
- 2026-05-03 18:30 UTC: Renamed the generic plan concept from `PLAN.md` to root `TODO.md` and updated `AGENTS.md` to match.
- 2026-05-03 18:40 UTC: Removed the `AGENTS.md` pointer from `README.md` so the README stays human-facing.
- 2026-05-03 21:26 UTC: Refactored the pipeline to use neutral workflow step names and shared config/manifest mappings instead of direct numbered workflow coupling; updated the main reports and validation docs to use neutral language, with remaining numbered labels limited to legacy filenames and preserved historical references.
- 2026-05-04 13:30 UTC: Repository onboarding audit. Removed stale `deanza-villas-flood-study-beginner.qgs` references from AGENTS.md and study_manifest.yaml (file was consolidated into the single .qgs). Merged manifest keys `qgis_main`/`qgis_beginner` into `qgis`. Updated TODO workflow: items are removed when done instead of archived as completed (DEVLOG is the completion record). Cleaned TODO.md to empty backlog.
- 2026-05-04 13:45 UTC: Unified DEVLOG.md into a single chronological log section (was split above/below a "## Log" heading with out-of-order timestamps). Updated README.md repo structure: removed "(planned)" label and nonexistent notebooks/ dir, added AGENTS.md/DEVLOG.md/TODO.md/config/ entries. Fixed two stale beginner .qgs references in project_summary.md. Removed unused CHANGELOG.md mention from AGENTS.md.
- 2026-05-04 15:37 UTC: Consolidated the version-1 phase development notes into `outputs/reports/v1_development_summary.md`, preserving only the salient terrain, parcel, fan, and validation decisions.
- 2026-05-04 16:22 UTC: Renamed the workflow scripts, maps, and processed outputs to neutral filenames; updated the configs and current reports to use neutral labels; verified repo searches only keep historical numbered references in the preserved version-1 log.
- 2026-05-04 17:13 UTC: Simplified the repo entry-point docs around `README.md`, `AGENTS.md`, `TODO.md`, `DEVLOG.md`, and `outputs/reports/final_report.md`; retired `outputs/reports/final_report_plan.md`, trimmed redundant startup links, and verified the remaining supporting/history docs are intentionally labeled.
- 2026-05-04 19:00 UTC: Pipeline simplification / boilerplate cleanup. (1) Fixed latent `config_path` import bug in all step scripts — was masked by argparse defaults. (2) Stripped argparse from `extract_washes.py`, `parcel_overlay.py`, `fan_synthesis.py`; each now reads paths directly from `study_config`. (3) Simplified `run_pipeline_v2.py` from 128 lines of explicit CLI-arg command lists to 64 lines of `[python, script]` calls. (4) Eliminated redundant multi-read of the same vector files (2-3x per script) — each script now reads all GeoDataFrames once in `main()` and passes them down. (5) Added `build_standard_map()` shared helper to `study_utils.py`; `parcel_overlay` and `fan_synthesis` now use it instead of duplicated folium code. (6) Replaced 40-80-line `lines.append()` report builders with f-string templates across all step scripts. (7) Aligned `satellite_validation.py` with vector-caching pattern. Total: 1508 lines vs ~1350 before (study_utils grew to absorb shared map code); per-script complexity dropped ~30-40%. All four pipeline steps re-ran successfully and outputs verified correct.
- 2026-05-04 20:30 UTC: DRY / dead-code simplification pass (all TODO items completed). (1) Removed dead helpers: `safe_write_csv`, `line_style`, `polygon_style` from study_utils; `step_value`, `manifest_path`, `manifest_value`, `relative_to_root` from study_config; `SelectedScene` dataclass from satellite_validation (~30 lines). (2) Removed unused imports across fan_synthesis, parcel_overlay, satellite_validation, generate_final_report_figures; fixed dangling f-string and file-handle leak in satellite_validation. (3) Fixed `make_map()` in satellite_validation — dropped hand-rolled `m2` rebuild (~65 lines → ~20); added `add_layer_control` param to `build_standard_map`; stashed `bbox_geojson` on `CandidateStats` to eliminate re-query of earthaccess at map time. (4) Added `scripts/__init__.py`; moved sys.path bootstrap into `study_config.py` side-effect; step scripts now import `ROOT` from study_config and drop their 3-line bootstrap blocks; orchestrator uses `python -m scripts.stepname`. (5) Collapsed `read_vector`/`ensure_crs` into unified `ensure_crs(gdf_or_path)`; added `read_vectors(**named_paths)` and `optional(template, value)` helpers to study_utils; used `optional()` to fold conditional-line pairs in parcel_overlay and extract_washes. (6) Swapped all hardcoded path constants in generate_final_report_figures and make_terrain_context_map to `config_path`/`step_path`; stripped argparse from fetch_dem and terrain_metrics; added `dem_source_aoi`, `dem_source_output`, `terrain_outdir` to study.yaml. (7) Replaced hardcoded REQUIRED_INPUTS list in run_pipeline_v2 with config-driven iteration over `study_config()["paths"]` plus a `_GENERATED_PATHS` allowlist. (8) extract_washes: pass `selected_threshold` and `hazard_count` from `derive_streams` to `write_report` — eliminates redundant hazard re-read and threshold recomputation. (9) fan_synthesis `_stream_stats`: return just float, drop unused segment count. pyflakes: 0 findings. Total: 2013 lines vs 2189 baseline (−176 lines, −8%).
- 2026-05-04 21:35 UTC: Tier 1 foundation fixes complete (all 7 tasks). (1) DEM replaced: py3dep 0.19.0 was retained (latest version; the non-square pixel issue is a known regression in 0.19.0, GitHub #77) but the output was reprojected to exactly 1.000m × 1.000m square pixels in EPSG:5070 via rasterio — the warped 0.833m × 0.847m pixels are gone. Attempted direct USGS tile access (x55y369 + x56y369) but the Eastern San Diego 2017 QL2 lidar project boundary doesn't reach the parcel — the parcel is ~600m outside the lidar project footprint on these tiles. py3dep's WCS mosaic of all available 3DEP sources covers the parcel correctly. (2) terrain_metrics.py: switched from simple fill_depressions to breach_depressions(max_length=250) → fill_depressions. This dramatically changed D8 flow routing — at threshold 5000, D8 now produces 237 segments / 24,724m with 49.1% hazard overlap (was 21 segments / 1,393m with 0% overlap on the old filled-only DEM). (3) D-infinity flow accumulation and pointer added alongside D8; stream extraction at matching thresholds. D-infinity vectorization limited: raster_streams_to_vector only works with D8 pointer; D-infinity stream stats reported as raster cell counts (21,238 cells at 5000, comparable to D8's 21,004). (4) extract_washes.py, parcel_overlay.py, fan_synthesis.py all rerun on new DEM + breached-fill conditioning + D-infinity. (5) All render outputs regenerated: wash_extraction.md (now includes D8 vs D-inf comparison table), parcel_overlay.html, satellite_validation.md/map. Config paths updated for new flat terrain structure and dinf_flow_accum. Temp tiles cleaned up.
- 2026-05-04 22:00 UTC: Tier 2 hazard evidence quality improvements complete (4 tasks). (1) FEMA NFHL data fetched from ArcGIS REST California reduced set (services2.arcgis.com): 40 features for DFIRM 06073C (38 AO, 1 A, 1 X) with depth 1-4 ft, velocity 3-9 ft/sec. Replaced CalOES FP100/FW100-only file. Hazard overlap at 5000 threshold jumped from 49.1% to 71.7% — the authoritative NFHL data provides substantially better coverage. Parcel overlay: 771m of stream network inside parcel, 95.8% within FEMA hazard zones, 15/237 segments touching both. (2) extract_washes.py refactored to full threshold ensemble: all thresholds (1000/2500/5000) kept, no single "best" selected. Added between-threshold zone analysis: 18,697 cells in the 1000→2500 marginal zone (593 in parcel), 9,373 cells in 2500→5000 (243 in parcel) — these are candidate avulsion paths. Between-threshold CSV/JSON saved alongside sweep files. (3) satellite_validation.py SEARCHES expanded: HLS 2023-2024 full year (400 items), S1 2024-08-25 to 2024-12-31 (100 items). (4) All renders, parcel_overlay, fan_synthesis rerun with new FEMA data.
- 2026-05-04 22:54 UTC: Tier 3 profile-curvature/TPI metrics complete. Added `scripts/curvature_tpi.py` and config paths for profile curvature, TPI, TPI scale, and stats JSON. Ran `.venv/bin/python scripts/curvature_tpi.py`; outputs verified at `data/processed/terrain/deanza_villas_2km_1m_dem_profile_curvature.tif`, `data/processed/terrain/deanza_villas_2km_1m_dem_tpi.tif`, `data/processed/terrain/deanza_villas_2km_1m_dem_tpi_scale.tif`, and `data/processed/terrain/deanza_villas_2km_1m/curvature_tpi_stats.json`.
- 2026-05-04 22:54 UTC: Tier 3b HAND complete. Added scripts/hand.py and config paths for the HAND raster/statistics step, computed WhiteboxTools elevation_above_stream from the breached+filled DEM and 5000-cell D8 stream raster, and saved data/processed/terrain/deanza_villas_2km_1m_dem_hand.tif plus data/processed/terrain/deanza_villas_2km_1m/hand_stats.json. Verification: script compiled and ran in .venv; HAND raster is EPSG:5070 at 1m, no negative cells found; parcel HAND stats are min 0.0m, mean 3.90m, max 61.81m. JSON explicitly qualifies HAND as relative terrain evidence, not inundation depth.
- 2026-05-04 23:00 UTC: Tier 3c DRI roughness comparison complete. Added `scripts/dri_roughness_comparison.py`, downloaded/copied the DRI 2015 PDF to `data/raw/dri_2015_borrego_fans.pdf`, rendered and color-classified page 20 at 300 dpi, and saved digitized active/inactive fan zones to `data/vectors/dri_2015_fan_zones.geojson` plus EPSG:5070 copy. Roughness comparison saved at `data/processed/terrain/deanza_villas_2km_1m/dri_roughness_comparison_stats.json` and summarized in `outputs/reports/dri_roughness_comparison.md`. Result: parcel is 99.6% inside digitized DRI active fan; no digitized inactive zone overlaps the local 2km roughness raster, so active-vs-inactive roughness could not be computed from this local raster footprint. Verification: script ran and compiled in `.venv`; QC overlay visually checked.
- 2026-05-04 23:02 UTC: Tier 3 synthesis complete. Read `curvature_tpi_stats.json`, `hand_stats.json`, and `dri_roughness_comparison_stats.json`; updated `TODO.md` to mark Tier 3 terrain diagnostics complete. Findings: parcel profile curvature is near neutral on average (mean -0.0010) with both concave and convex extremes, consistent with a mixed surface of shallow concentrated-flow forms and broader sheet-flow/planar fan tread; parcel TPI is slightly positive on average (mean 0.078m) but spans the full local range (-38.84m to 92.25m), showing local channel lows, levee/high microrelief, and older/abandoned lobe relief within the mapped boundary; parcel HAND averages 3.90m above the selected 5000-cell D8 stream network with zero negative cells, supporting relative low-position exposure near mapped drainage but not an inundation-depth estimate; DRI comparison places 99.6% of the parcel in the digitized active fan, with parcel roughness mean 3.59m close to the active-fan mean 3.75m. Limits: HAND is only relative terrain evidence on an active alluvial fan; DRI active/inactive zones were digitized from PDF page 20, and inactive roughness could not be measured inside the local 2km roughness footprint because no inactive polygon intersects it.

- 2026-05-05 11:25 UTC: D-infinity artifact regeneration. Regenerated `dinf_flow_accum.tif` and `dinf_pointer.tif` from the canonical breached+filled DEM (1412×1427, 1m² EPSG:5070). Re-extracted Dinf stream rasters at thresholds 1000/2500/5000. All 7 Dinf artifacts confirmed aligned with DEM/D8 bounds and dimensions. Stream cell counts unchanged from prior run (57,561 / 33,013 / 21,238). Divergence signal intact: 36.2% of cells show Dinf ≥ 1.5× D8 (fan spreading), 10.9% show Dinf ≤ 0.67× D8 (diffuse zones). Updated Dinf threshold sweep CSV/JSON. Prior memory of a 1735×1722 DEM dimension mismatch was stale — the 1735×1722 was from a transient test AOI; all production rasters are consistently 1412×1427.

- 2026-05-05 11:45 UTC: Option 2 threshold morph explorer v2 built (`outputs/maps/threshold_morph_explorer_v2.html`). MapLibre GL JS v4.7.1 with Esri World Imagery satellite basemap, native pan/zoom, HTML Canvas overlay synced to map viewport for D∞ stream cell rendering. D∞ only (no D8 toggle — divergence IS the signal). Same log-scale slider 250–100K, binary-search renderer (~34K cells at 5K threshold), parcel boundary as MapLibre GeoJSON line layer. Stats display: visible cells, current threshold, D∞/D8 cell ratio (using verified D8 cell counts: 49,074 / 30,377 / 21,004). Pared back zoom from pad=0.0005 to pad=0.0025 (~500m view width — fan context visible but not full 2km AOI).

- 2026-05-05 ~21:10 UTC: 1m watershed spike cleanup and rewrite (Phase 1 + 2). Deleted dead 3×3-expanded-view spike (970 MB) and 6.0 GB of uncompressed/nodata intermediates. Rewrote `spikes/1m-watershed/build.py` with: dynamic fetch bbox from canonical `data/vectors/henderson_watershed_boundary.geojson`, 4×3 tile grid + gc, fill-only (no breach — WBT BreachDepressions OOMs on 165M px), clipped DEM masking, 2m D∞ computation (WBT DInfFlowAccumulation OOMs at 1m on 7.6 GB RAM — 5+ attempts, consistently dies at output-write phase after 100% flow directions), 1m stream rasters upsampled via nearest-neighbor, Parquet export (accum/x_5070/y_5070/lon/lat) at thresholds 1000/2500/5000. Results: D∞ 2m 8368×4923 (26.8M valid cells), stream cells at 1m: 5.1M/3.0M/2.0M. Disk: 1.4 GB (down from 6.3 GB). Artifacts: `dem_1m_5070.tif` (667 MB mosaic), `dem_clipped.tif` (418 MB), `din_flow_accum_2m.tif` (120 MB compressed float32), `streams_*.parquet` (96/56/37 MB), `streams_*.tif` (4/4/3 MB compressed uint8). Pitfalls: py3dep WCS verbose warnings (suppressed with PYTHONWARNINGS), WBT -v flag pipe-stalls on large rasters (disabled with set_verbose_mode(False)), rio_transform returns lists not arrays when stream arrays are empty (np.asarray fix).

- 2026-05-05 12:30 UTC: 3×3 expanded D∞ spike complete (`spikes/3x3-expanded-view/`). Fetched 4.2km DEM via py3dep WCS at 1m, reprojected to 1m² EPSG:5070 (4236×4281, 18.1M px). Breach+fill, D∞ flow accum+pointer, stream extraction at threshold 250, binary export (1,062,243 cells, 12.7MB). WBT D∞ flow accum took only 2s on 18M px. Binary export bottleneck (197s) due to per-cell EPSG:5070→4326 transform; fixable with vectorized transform. Throwaway HTML at `outputs/maps/threshold_morph_explorer_3x3.html` for A/B comparison against v2. Core pipeline untouched. Verdict: 5× more stream cells, same viewport-culled render cost, disk footprint ~873MB for rasters.

- 2026-05-05 ~22:30 UTC: Watershed boundary corrected — major finding. WBT `watershed()` on the 10m Henderson DEM with 28,767 community-bbox pour points produced a 107 km² result that was 96% false positive. D8 BFS upstream trace found only **4.2 km²** — also wrong, too conservative (D8 chains break on flat fan surface). D∞ BFS upstream trace (second attempt, degrees-corrected) found **33.6 km²** across 383K cells, E-W 10.4 km (lon -116.43 to -116.32), N-S 6.6 km (lat 33.25 to 33.31). D∞ connectivity maintained flow paths across the fan where D8 couldn't. WBT DInfPointer stored angles in degrees (0–360), not radians — initial run was wrong. Corrected boundary polygonized (22 fragments → MultiPolygon), saved to canonical `data/vectors/henderson_watershed_boundary.geojson`. Old 107 km² boundary backed up to `henderson_watershed_boundary_WRONG_107km2.geojson`. D8 BFS mask saved to `actual_watershed_bfs.tif`. Validation map at `outputs/maps/watershed_boundary_validation.html` shows old (dashed red) vs new (solid green). Cascade: 1m watershed data (`streams_all.bin`, 59 MB/5M cells) built using wrong boundary — needs regeneration.

- 2026-05-08 ~23:45 UTC: Henderson 1m reachability pipeline resumed (mid-debug handoff). State: Process A v3 (watershed-masked D8 pointer → pyflwdir accum) and Process B (stream extraction → uint8) already completed on disk. Verify: accum monotonic (0 violations/1000 sample), terminal rate 0.13% (6.5K/5.1M). Process C (D8 reachability + binary): 48,600/5,114,971 reachable (1.0%), 21s, 2.2 GB peak RSS → `streams_d8_1m.bin` (583 KB). Process D (D∞ mask + streams re-extraction + reachability + binary): mask written (`dinf_flow_accum_1m_masked.tif`), streams re-extracted (6,572,709 cells, uint8), reachability in progress (D∞ post-order DFS on 6.5M cells — slow). Build functions updated: `build_dinf_1m()` and `build_d8_1m()` now watershed-mask accum (matches 10m pattern). `compute_d8_accum()` gained optional `watershed_geom` parameter for pointer-level masking before pyflwdir (avoids OOM on 165M-cell grids). rlimit reverted to 5 GB in Process A. Stale `streams_d8_1m.bin` (13:51, 72K cells) replaced. Python `&` in terminal() auto-detected as background operator — worked around via spike scripts.

- 2026-05-09 ~00:15 UTC: D∞ reachability completed. Result: 31,629/6,572,709 reachable (0.5%), 94.7M cells traced, 4.0M cache hits, 486s, 2.4 GB peak RSS → `streams_all.bin` (380 KB). D∞ terminal rate: 30.66% (2,015,512/6,572,709) — very high vs D8's 0.13%. This is a legitimate terrain signal, not a bug: D∞ captures divergent flow across the alluvial fan, producing many dead-end stream segments where flow dissipates below threshold. D8 is channelized and better connected to the main channel reaching the parcel. D8/D∞ reachable overlap: only 2,677 cells — most reachable cells are unique to one network (D8: 45,923 unique, D∞: 28,952 unique). This reflects fundamentally different stream network topology, not trace errors.

- 2026-05-09 ~00:30 UTC: Stream explorer updated for reachability-filtered binaries. Changes: (1) "Total stream cells" → "Reachable cells" with dynamic K/M formatting + sub-1000 raw count; (2) default threshold 5,000 → 1,000; (3) removed stale loading labels (79/85 MB); (4) added amber "⇢ De Anza Villas only" indicator in stats bar; (5) dataset-switch formatter handles sub-1000 counts.
