# TODO.md

Use this file as the queued-pending work list for the current effort.

Suggested format:
- Keep items short and ordered by priority.
- Use checkboxes or a simple backlog list.
- Mark items `in_progress` while working on them. When done, remove them — `DEVLOG.md` records the outcome.
- Add or reconcile items when the same request comes up again.

Recommended relationship to other repo logs:
- `DEVLOG.md` = what actually happened, with short timestamped notes
- `TODO.md` = what is queued or pending (not an archive of completed work)
- `CHANGELOG.md` = public release/history notes, if the project uses one

## Backlog

- Graceful failure on empty/nodata/ridge contributing area (pipeline crashes mid-flow-accumulation rather than reporting a clean error)
- Test pipeline on substantially different terrain (Appalachians, karst, glacial) — Jacksonville coastal plain is benign
- Consider `BreachDepressionsLeastCost` with max breach length as middle-ground hydro strategy (between aggressive breach_then_fill and conservative fill_only)
