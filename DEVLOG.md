# Active development log

Use this file as the rolling project work log for ongoing changes, status updates, and verification notes.

Suggested format for entries:
- `YYYY-MM-DD HH:MM UTC: <brief status update>`
- Include what changed, why it changed, and what was verified.

Guidance:
- Keep this as the generic long-lived log for future work.
- Use task-specific plans only when a one-off effort needs its own checklist or migration note.
- Retire one-off plan files when they are no longer useful, but keep this log as the standard place for active progress.

- 2026-05-03 17:52 UTC: Created `config/study.yaml`, `config/study_manifest.yaml`, `scripts/study_config.py`, `scripts/study_utils.py`, and `scripts/run_pipeline_v2.py` to centralize canonical paths and orchestration.
- 2026-05-03 17:52 UTC: Refactored the phase scripts to import the shared config/helpers instead of repeating hardcoded study paths.
- 2026-05-03 17:52 UTC: Reran the v2 pipeline successfully in the project virtualenv; the canonical reports and HTML maps were regenerated.
- 2026-05-03 21:26 UTC: Refactored the pipeline to use neutral workflow step names and shared config/manifest mappings instead of direct `phase1` through `phase4` coupling; updated the main reports and validation docs to use neutral language, with remaining phase-number strings limited to legacy filenames and historical references.
- 2026-05-03 17:59 UTC: Retired the temporary v2 plan after moving its historical status notes into `DEVLOG.md`.

## Log

- 2026-05-03 18:00 UTC: Created as the canonical rolling dev log after the v2 pipeline plan was completed.
- 2026-05-03 18:10 UTC: Moved the rolling log to root `DEVLOG.md`, linked it from `README.md`, and made `AGENTS.md` point to it as the generic active-work log.
- 2026-05-03 18:20 UTC: Added generic plan-file guidance to `AGENTS.md` so queued work can live in `TODO.md` and material execution notes can continue in `DEVLOG.md`.
- 2026-05-03 18:30 UTC: Renamed the generic plan concept from `PLAN.md` to root `TODO.md` and updated `AGENTS.md` to match.
- 2026-05-03 18:40 UTC: Removed the `AGENTS.md` pointer from `README.md` so the README stays human-facing.
- 2026-05-04 15:37 UTC: Consolidated the version-1 phase development notes into `outputs/reports/v1_development_summary.md`, preserving only the salient terrain, parcel, fan, and validation decisions.
