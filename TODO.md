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

## Implementation plan: remove hardcoded phase labels
- [x] Step 1 — inventory the coupling points: run a repo-wide search for `phase1` through `phase4`, then classify each hit as (a) orchestration logic, (b) shared config/manifest, (c) script/file name, (d) output path, or (e) human-facing wording. Record the full hit list in this TODO before editing code.
- [x] Step 2 — define neutral step IDs and the canonical mapping: update `config/study.yaml`, `config/study_manifest.yaml`, and `scripts/study_config.py` so the pipeline can address work by purpose instead of phase number. Use stable neutral names for the workflow stages (for example: terrain context, wash extraction, parcel overlay, fan synthesis, satellite validation) and keep the existing output filenames as canonical deliverables unless a rename is truly needed.
- [x] Step 3 — decouple orchestration first: refactor `scripts/run_pipeline_v2.py` and any shared helpers it relies on so ordering, input validation, and canonical output lookup use the neutral mapping rather than literal `phase1` through `phase4` references.
- [x] Step 4 — refactor the stage scripts: update `scripts/phase2_extract_washes.py`, `scripts/phase3_parcel_overlay.py`, `scripts/phase3_fan_synthesis.py`, `scripts/phase4_satellite_validation.py`, and any phase-related helper scripts so they consume the shared neutral step/config data instead of embedding phase-number assumptions. Keep compatibility shims only where a historical filename or CLI entry point must remain.
- [x] Step 5 — sweep the docs and generated reports: update `README.md`, `outputs/reports/project_summary.md`, `outputs/reports/final_report.md`, `outputs/reports/phase1_context.md`, `outputs/reports/phase2_wash_extraction.md`, `outputs/reports/phase3_parcel_overlay.md`, `outputs/reports/phase3_fan_synthesis.md`, `outputs/reports/phase4_satellite_validation.md`, and the handoff/status notes under `outputs/reports/` so phase numbers are replaced with neutral language unless the text is explicitly preserved history.
- [x] Step 6 — verify nothing phase-coupled remains: rerun the repo search for `phase1` through `phase4`, confirm any remaining matches are intentional filenames or historical references, then append a timestamped summary of the refactor and any deliberate exceptions to `DEVLOG.md`.

Completed refactor note: the remaining `phase1`–`phase4` matches are now limited to legacy filenames, canonical output paths, and historical status notes. The orchestration code, shared helpers, and report prose now use neutral step names.
