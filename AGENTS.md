# AGENTS.md

This file is the fast entry point for agents working in this repository.

Read this first, then use the linked project docs below to orient yourself quickly.

## What this repo is
This is the Borrego Springs / De Anza Villas flood study. The work is geospatial, terrain-driven, and centered on canonical parcel boundaries, canonical output paths, and reproducible workflow scripts.

## Read first
1. `README.md` — broad project overview and canonical deliverables
2. `TODO.md` — queued work for the current effort
3. `DEVLOG.md` — rolling active development log for ongoing work

## Canonical working conventions
- Prefer canonical paths from `config/study.yaml` and `config/study_manifest.yaml`.
- Keep one canonical file per deliverable when possible.
- Do not reintroduce repeated hardcoded paths into workflow scripts.
- Preserve exact parcel boundaries when available; do not replace them with approximate footprints.
- Keep report/map outputs stable so links do not churn.
- If the active work changes something material, append a short timestamped note to `DEVLOG.md`.

## Planning workflow
Use a TODO file when there are pending changes that should be queued before execution.

Recommended conventions:
- `TODO.md` = queued or pending work for the current effort
- `DEVLOG.md` = what actually happened, with short timestamped notes

Operating rules:
- Put requested future work into `TODO.md` as a checklist or ordered backlog.
- Re-read `TODO.md` before starting a new round of work so queued items stay in view.
- When the user asks for the same work again, use `TODO.md` to reconcile what is already queued instead of duplicating tasks.
- Mark items `in_progress` while working on them. When done, remove them from `TODO.md` entirely — `DEVLOG.md` is the record of what was completed and when.
- Treat one-off migration or cleanup plans as temporary; retire them when the work is done.
- Before forming a hypothesis about why an external tool is producing wrong output, stratify the observed disagreements by relevant terrain/data covariates and check whether the failure pattern is uniform (suggesting your code) or clustered (suggesting a real edge case).

## Where to look for the main artifacts
- `config/study.yaml` — stable study paths, CRS, thresholds, and output names
- `config/study_manifest.yaml` — canonical layers and deliverables
- `scripts/study_config.py` — shared config access helpers
- `scripts/study_utils.py` — shared geospatial helpers
- `scripts/__main__.py` — study orchestrator (`python -m scripts` from repo root)
- `DEVLOG.md` — rolling development log
- `TODO.md` — active backlog for queued work, if present
- `outputs/reports/final_report.md` — canonical final narrative
- `outputs/reports/project_summary.md` — supporting summary and file map
- `outputs/reports/v1_development_summary.md` — historical background only
- `outputs/reports/` — narrative reports and one-off logs/plans
- `outputs/maps/` — HTML maps
- `data/processed/terrain/` — derived rasters and vectors
- `deanza-villas-flood-study.qgs` — QGIS project (beginner-friendly default view)

## Current project status
The v2 cleanup and end-to-end rerun completed successfully. Use the rolling dev log for new progress notes.

## Reporting style
When you make changes:
- update `DEVLOG.md` for ongoing work or material changes
- keep notes short and timestamped
- mention verification steps and any warnings that matter for future work
- avoid splitting status across multiple competing docs