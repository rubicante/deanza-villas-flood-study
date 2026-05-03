# Borrego Flood Study v2 Pipeline Plan

## Purpose

This plan describes a simpler, more unified second version of the Borrego Springs / De Anza Villas flood-study pipeline.

The main goals are to:
- remove repeated path and CRS declarations,
- keep one canonical source of truth for inputs and outputs,
- reduce script-to-script drift,
- make reruns and future edits easier,
- preserve the current analysis logic while tightening the structure around it.

## Current status

- Implementation and end-to-end rerun are complete.
- The shared study config, manifest, helper module, and v2 runner are in place.
- Phase scripts now read their canonical paths from the shared config instead of repeating hardcoded locations.
- The v2 pipeline completed successfully in the project virtualenv.
- Manual GUI open checks for the QGIS project files still need a local QGIS session.

## Implementation checklist

### 0. Baseline freeze

- [ ] Confirm the current canonical outputs and file names are still the intended ones.
- [ ] Confirm both QGIS project files open cleanly in QGIS 3.x.
- [ ] Record any intended renames only in the manifest/config, not as new competing artifacts.

### 1. Shared config and manifest

- [ ] Create `config/study.yaml` with stable paths, CRS, thresholds, and output names.
- [ ] Create `config/study_manifest.yaml` with canonical layer and deliverable names.
- [ ] Move repeated path and parameter declarations out of the phase scripts.
- [ ] Update the phase scripts to read from the shared config/manifest.

### 2. Shared geospatial helpers

- [ ] Create `scripts/study_utils.py`.
- [ ] Move repeated CRS, geometry, raster, and write helpers into the shared module.
- [ ] Keep the helper surface small and phase-agnostic.
- [ ] Add a quick self-check for helper behavior if needed.

### 3. Phase script refactors

- [ ] Refactor `scripts/phase2_extract_washes.py` to use the shared config and helpers.
- [ ] Refactor `scripts/phase3_parcel_overlay.py` to use the manifest and shared overlay helpers.
- [ ] Refactor `scripts/phase3_fan_synthesis.py` to use shared raster/stat helpers.
- [ ] Refactor `scripts/phase4_satellite_validation.py` to use shared config and canonical output paths.

### 4. Orchestrator

- [ ] Create `scripts/run_pipeline_v2.py`.
- [ ] Make it load the config and manifest once.
- [ ] Make it verify required inputs before running phases.
- [ ] Wire the phases in the current analysis order.
- [ ] Make it fail fast on missing inputs or broken outputs.

### 5. Outputs and QGIS

- [ ] Normalize output naming so there is one canonical file per deliverable.
- [ ] Update report links to point to the canonical artifacts.
- [ ] Refresh `deanza-villas-flood-study.qgs` if any layer names or paths change.
- [ ] Refresh `deanza-villas-flood-study-beginner.qgs` to stay aligned with the main project.

### 6. Verification

- [ ] Parse both `.qgs` files as XML.
- [ ] Run the v2 pipeline end to end.
- [ ] Confirm the key phase outputs are recreated.
- [ ] Compare the core metrics against the current baseline.
- [ ] Confirm HTML map and report links resolve to real files.

### 7. Finish

- [ ] Commit the v2 cleanup baseline.
- [ ] Push the branch to GitHub.
- [ ] Add a short status update to this same file describing the outcome.

## Status log

- 2026-05-03 17:52 UTC: Created `config/study.yaml`, `config/study_manifest.yaml`, `scripts/study_config.py`, `scripts/study_utils.py`, and `scripts/run_pipeline_v2.py` to centralize canonical paths and orchestration.
- 2026-05-03 17:52 UTC: Refactored the phase scripts to import the shared config/helpers instead of repeating hardcoded study paths.
- 2026-05-03 17:52 UTC: Reran the v2 pipeline successfully in the project virtualenv; the canonical reports and HTML maps were regenerated.

## What stays the same

- EPSG:5070 as the common study CRS.
- The same core evidence chain:
  - terrain / DEM derivatives,
  - wash extraction,
  - parcel overlay,
  - fan-activity synthesis,
  - satellite validation.
- The canonical parcel boundary and parcel polygons.
- The selected stream network at the chosen accumulation threshold.
- The final report and HTML maps as end-user deliverables.

## What changes in v2

- One shared configuration file for paths, CRS, thresholds, and output names.
- One canonical study manifest that names the authoritative layers and deliverables.
- One shared geospatial helper module for common geometry/raster operations.
- One orchestrator script that runs the phases in order.
- One consistent style config for report/map colors and labeling fields.
- One canonical QGIS project workflow with a beginner view and a main project view.

## Proposed sections

1. v2 architecture and canonical files
2. Shared configuration and manifest
3. Shared geospatial helpers
4. Phase scripts refactor
5. Orchestrator / pipeline runner
6. Output naming and canonical artifacts
7. QGIS project integration
8. Verification and regression checks
9. Migration order

## 1) v2 architecture and canonical files

The v2 pipeline should treat the study as a small geospatial product with a single canonical backbone.

Canonical backbone files:
- `config/study.yaml` or `config/study.json` for all stable paths and parameters
- `config/study_manifest.yaml` for canonical layer/output names
- `scripts/study_utils.py` for shared helpers
- `scripts/run_pipeline_v2.py` for orchestration
- `outputs/reports/final_report.md` as the final narrative deliverable
- `deanza-villas-flood-study.qgs` as the primary QGIS project
- `deanza-villas-flood-study-beginner.qgs` as the beginner-friendly QGIS project

Why:
- reduces duplicated constants across phase scripts,
- makes it clear which files are authoritative,
- lets future edits happen in one place instead of four.

## 2) Shared configuration and manifest

### Goal
Move repeated paths, thresholds, and layer names into one shared config.

### Contents
The config should include:
- project root
- common CRS (`EPSG:5070`)
- AOI paths
- parcel boundary and parcel polygon paths
- terrain raster paths
- hazard layer paths
- satellite validation paths
- canonical output paths
- stream thresholds to sweep
- selected canonical threshold

### Manifest contents
The manifest should identify:
- canonical dissolved parcel boundary
- canonical parcel polygon exposure layer
- canonical selected stream network
- canonical hazard layer
- canonical HTML maps
- canonical markdown reports
- canonical QGIS files

### Why this helps
- every script reads the same source of truth,
- renaming a file becomes a single edit,
- canonical outputs are explicit and easy to browse.

## 3) Shared geospatial helpers

### Goal
Pull repetitive geometry/raster code into a helper module.

### Candidate helpers
- `read_vector(path, crs=5070)`
- `read_raster(path)`
- `ensure_crs(gdf, crs=5070)`
- `union_geometry(gdf)`
- `line_length_metrics(lines, polygons)`
- `raster_mask_stats(raster, geom)`
- `safe_write_csv(df, path)`
- `safe_write_json(obj, path)`
- `layer_style_config()`

### Why this helps
- reduces copy-paste across phase 2–4 scripts,
- keeps CRS handling consistent,
- keeps intersection logic and summary logic uniform.

## 4) Phase scripts refactor

### Phase 2 script
Refactor `scripts/phase2_extract_washes.py` so it:
- reads thresholds and paths from the shared config,
- uses helper functions for CRS and geometry operations,
- only contains the phase-specific threshold sweep and selection logic.

### Phase 3 parcel overlay script
Refactor `scripts/phase3_parcel_overlay.py` so it:
- reads canonical parcel and hazard layers from the manifest,
- uses shared helpers for length/intersection calculations,
- only computes parcel-specific overlay metrics.

### Phase 3 fan synthesis script
Refactor `scripts/phase3_fan_synthesis.py` so it:
- uses shared raster-stat helpers,
- only computes terrain summaries and roughness,
- reads the selected network and parcel layers from the manifest.

### Phase 4 satellite validation script
Refactor `scripts/phase4_satellite_validation.py` so it:
- uses shared config for search windows and output paths,
- keeps discovery / download / masking / counting logic isolated,
- writes summary tables through common utilities.

### Why this helps
- the phase scripts become smaller and easier to read,
- their inputs/outputs stay aligned,
- the pipeline becomes easier to extend later.

## 5) Orchestrator / pipeline runner

### Goal
Replace manual phase-by-phase execution with one top-level runner.

### Proposed behavior
A runner like `scripts/run_pipeline_v2.py` should:
1. load config and manifest,
2. verify required inputs exist,
3. run phase 2,
4. run phase 3 overlay,
5. run phase 3 fan synthesis,
6. run phase 4 validation,
7. build final report pointers,
8. optionally refresh the QGIS project files.

### Why this helps
- one command rebuilds the study,
- fewer chances to forget an intermediate step,
- easier to hand off and easier to debug.

## 6) Output naming and canonical artifacts

### Canonical names to keep stable
- `phase2_channel_context.html`
- `phase3_parcel_context.html`
- `phase3_fan_synthesis.html`
- `phase4_satellite_validation.html`
- `final_report.md`
- `deanza-villas-flood-study.qgs`
- `deanza-villas-flood-study-beginner.qgs`

### Naming rules
- use one canonical output per deliverable type,
- use `selected`, `canonical`, or `beginner` only when it adds real meaning,
- avoid multiple competing “final” files,
- keep phase output names stable so links do not churn.

### Why this helps
- simpler browsing,
- easier report linking,
- fewer artifacts to maintain.

## 7) QGIS project integration

### Goal
Keep QGIS usable for both expert and beginner review.

### Main project
- default to the authoritative study layers,
- keep the parcel boundary readable,
- keep the selected stream network visible,
- preserve sensible layer order,
- maintain the canonical study extent.

### Beginner project
- keep the canvas centered on the local study area,
- hide clutter-heavy layers by default,
- use more transparent fills,
- emphasize the boundary, hazard polygons, and stream network.

### Styling strategy
- define colors in one style config,
- use existing label fields only,
- keep labels readable with simple halos/buffers if needed,
- avoid over-styling layers that are not critical to orientation.

### Why this helps
- the QGIS handoff becomes less confusing,
- both projects stay visually consistent,
- fewer edits are needed if layer names change.

## 8) Verification and regression checks

### Basic checks
- parse all `.qgs` files as XML,
- confirm all config paths resolve,
- confirm all canonical outputs are present after a full run,
- confirm report links point to real files,
- confirm the selected network is still the threshold 5000 result unless intentionally changed.

### Geospatial checks
- verify CRS is still EPSG:5070 across derived layers,
- verify parcel overlay metrics are unchanged or intentionally updated,
- verify the fan synthesis tables still align with the parcel overlay numbers,
- verify the satellite selected JSON still matches the report narrative.

### Why this helps
- catches accidental drift,
- makes future edits safer,
- keeps the pipeline reproducible.

## 9) Migration order

### Step 1: Freeze canonical outputs
- identify which files are authoritative today,
- stop naming new competing artifacts,
- record canonical file names in the manifest.

### Step 2: Add config + manifest
- create the shared config file,
- create the canonical manifest file,
- update scripts to read from them.

### Step 3: Add shared helper module
- extract read/CRS/intersection/stat helpers,
- switch phase scripts to use the helpers.

### Step 4: Add orchestrator
- build a single runner for phase 2–4,
- wire in report and map generation.

### Step 5: Tighten QGIS handoff
- make the main and beginner projects consume the canonical layer names,
- keep styles and extents aligned.

### Step 6: Run regression checks
- validate all outputs,
- inspect the HTML maps,
- confirm the report still tells the same story.

## Suggested implementation sequence

1. Create `config/study.yaml` and `config/study_manifest.yaml`.
2. Write `scripts/study_utils.py` with shared CRS and overlay helpers.
3. Refactor phase 2 to read shared config.
4. Refactor phase 3 overlay and fan synthesis to use shared helpers.
5. Refactor phase 4 to use shared config and manifest paths.
6. Add `scripts/run_pipeline_v2.py`.
7. Update the final report links and any canonical references.
8. Rebuild and verify all outputs.
9. Commit the v2 pipeline as a self-contained baseline.

## Definition of done

The v2 pipeline is done when:
- one config controls the study paths and parameters,
- one manifest identifies the canonical outputs,
- the phase scripts are smaller and less repetitive,
- one runner can rebuild the study end-to-end,
- the QGIS files still open cleanly,
- the final report and HTML maps still match the same results,
- the pipeline is easier for future work than the current version.

## Notes

This v2 plan is intentionally conservative. It is not a rewrite of the analysis logic. It is a cleanup and unification pass that preserves the current evidence chain while reducing boilerplate and ambiguity.
