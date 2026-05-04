# TODO.md

Use this file as the queued-pending work list for the current effort.

Suggested format:
- Keep items short and ordered by priority.
- Use checkboxes or a simple backlog list.
- Mark items `in_progress` when work starts and `completed` when done.
- Add or reconcile items when the same request comes up again.

Recommended relationship to other repo logs:
- `DEVLOG.md` = what actually happened, with short timestamped notes
- `TODO.md` = what is queued or pending
- `CHANGELOG.md` = public release/history notes, if the project uses one

## Implementation plan: remove historical numbered labels
- [x] Step 1 — inventory the coupling points: run a repo-wide search for historical numbered labels, then classify each hit as (a) orchestration logic, (b) shared config/manifest, (c) script/file name, (d) output path, or (e) human-facing wording. Record the full hit list in this TODO before editing code.
- [x] Step 2 — define neutral step IDs and the canonical mapping: update `config/study.yaml`, `config/study_manifest.yaml`, and `scripts/study_config.py` so the pipeline can address work by purpose instead of a numbered workflow label. Use stable neutral names for the workflow stages (for example: terrain context, wash extraction, parcel overlay, fan synthesis, satellite validation) and keep the existing output filenames as canonical deliverables unless a rename is truly needed.
- [x] Step 3 — decouple orchestration first: refactor `scripts/run_pipeline_v2.py` and any shared helpers it relies on so ordering, input validation, and canonical output lookup use the neutral mapping rather than literal numbered workflow references.
- [x] Step 4 — refactor the stage scripts: update `scripts/extract_washes.py`, `scripts/parcel_overlay.py`, `scripts/fan_synthesis.py`, `scripts/satellite_validation.py`, and any workflow-related helper scripts so they consume the shared neutral step/config data instead of embedding numbered-workflow assumptions. Keep compatibility shims only where a historical filename or CLI entry point must remain.
- [x] Step 5 — sweep the docs and generated reports: update `README.md`, `outputs/reports/project_summary.md`, `outputs/reports/final_report.md`, `outputs/maps/terrain_context.html`, `outputs/reports/wash_extraction.md`, `outputs/reports/parcel_overlay.md`, `outputs/reports/fan_synthesis.md`, `outputs/reports/satellite_validation.md`, and the handoff/status notes under `outputs/reports/` so historical labels are replaced with neutral language unless the text is explicitly preserved history.
- [x] Step 6 — verify nothing historically coupled remains: rerun the repo search for historical numbered labels, confirm any remaining matches are intentional filenames or historical references, then append a timestamped summary of the refactor and any deliberate exceptions to `DEVLOG.md`.

## Refactor plan: simplify repository entry points and artifact sprawl
- [x] Step 1 — inventory the current doc and output surface: read `README.md`, `AGENTS.md`, `DEVLOG.md`, `outputs/reports/project_summary.md`, `outputs/reports/final_report.md`, and `outputs/reports/v1_development_summary.md`; classify each as canonical, supporting, or historical, and note the retired `outputs/reports/final_report_plan.md` as a temporary artifact that is no longer part of the active surface.
- [x] Step 2 — choose the minimum canonical doc set: keep `README.md` as the human overview, `AGENTS.md` as the agent routing file, `TODO.md` as the queued-work list, `DEVLOG.md` as the active log, and `outputs/reports/final_report.md` as the canonical narrative; treat `outputs/reports/project_summary.md` as supporting and `outputs/reports/v1_development_summary.md` as historical.
- [x] Step 3 — collapse temporary planning and status notes: move durable checklist items into `TODO.md` or `DEVLOG.md`, retire the one-off final-report plan, and keep any remaining background notes explicitly historical.
- [x] Step 4 — simplify the startup path for new sessions: trim `README.md` and `AGENTS.md` so they point only to the files a fresh agent or human actually needs first, and remove redundant links to noncanonical artifacts.
- [x] Step 5 — sweep for stale or duplicate references: search the repo for retired filenames, duplicated doc pointers, and leftover historical labels in docs or report text; update the intentional ones and note the rest as preserved history.
- [x] Step 6 — verify the simplified structure: confirm the root docs now describe one clear path into the repo, then append a short timestamped note to `DEVLOG.md` once the cleanup lands.

Completed refactor note: the entry-point docs are now simplified around `README.md`, `AGENTS.md`, `TODO.md`, `DEVLOG.md`, and `outputs/reports/final_report.md`; `outputs/reports/project_summary.md` remains a supporting file map, `outputs/reports/v1_development_summary.md` is historical, and `outputs/reports/final_report_plan.md` has been retired.
