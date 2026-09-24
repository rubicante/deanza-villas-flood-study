# Development log

Rolling work log: what changed, why, and what was verified.
Format: `- YYYY-MM-DD HH:MM UTC: <what changed, why, what was verified>` (newest last).

## Prior architecture (2026-05-03 → 2026-05-12), condensed

The full entries are in git history: `git show d77ea00:DEVLOG.md`. They describe
an earlier `scripts/` + `config/study.yaml` pipeline (reports, folium maps, HAND,
curvature/TPI, satellite validation, DRI roughness) and a Henderson Canyon
watershed build, all since removed. Findings that still matter:

- **Methodology:** breach-then-fill beats fill-only on the fan (D8 FEMA hazard
  overlap 0% → 49%, 72% after the switch to FEMA NFHL). The native 3DEP 1m
  lidar misses parts of the canyons, hence merging every overlapping survey.
- **D∞ vs D8 on the fan:** a bulk ~29% "uphill" D∞ disagreement disappeared when
  stratified by local relief. D∞ agrees with D8 on relief >10 m and is only
  ambiguous on near-flat cells (a Tarboton 1997 edge case, not a WBT bug).
  Lesson: stratify disagreements by terrain before blaming the tool.
- **Watershed delineation:** community-bbox pour points gave a 107 km² result
  that was 96% false positive. The pipeline moved to the parcel → D∞ upstream
  trace → contributing area design used today (plan written 2026-05-09).
- **Reachability** (now `floodflow/experimental/`): fixed a D∞ cycle-detection
  cache-poisoning bug (2026-05-09; the three test grids in tests/). It's off by
  default because D8/D∞ routing on flat fan terrain often misses the parcel.
- **Performance:** a numba rewrite of the upstream trace (2026-05-09) fixed an
  OOM on a 165M-cell 1m pointer. The current `upstream.py` is pure Python again,
  which is fine at 10m (2 s) but would need that rewrite for a 1m trace
  (REFACTOR_PLAN §3.6).
- **Hard-won tool behaviours** (WBT SCA default, D8 hang, pointer nodata,
  relative paths, pipe stalls, rasterio list returns) are in AGENTS.md.

## Log

- 2026-09-24 UTC: Correctness pass from `REFACTOR_PLAN.md` §1 (items 1.1–1.12, plus a new 1.13). Pipeline: derived outputs are namespaced per parcel under `data/derived/runs/<parcel>/`; `docs/build_params.json` records each published binary's build params, and `build()` rebuilds when they differ. `all` now passes `parcel_fn`. The export boundary check now buffers in EPSG:5070 (it used to buffer 10°). `build()` defaults to `reachability_mode="none"`. The known-bad D8 backends (`auto`, `pyflwdir`) are gone. The D∞ verify now enforces accum[nbr] ≥ share × accum[cell] (0 violations on 30K checks of real WBT output; catches a reversed pointer in 2906/3000 paths). TNM queries paginate (the 25 km bootstrap extent returns 119 1m tiles, previously truncated at 100). Tile downloads go via `.part` files with a Content-Length check. Binary format v2 stores drainage area (m²) and origin-offset coordinates. The four published binaries were migrated v1→v2 in place (value × res², coordinates re-based; coordinates keep v1's ~0.7 m float32 quantization until the next regeneration). Explorer: reads v2, slider runs 250 m² to 10 km² with log-positioned ticks, default 10 ha (the same view as the old 1,000-cell default on D∞ 10m), "Stream cells" shows the active dataset, cells are centred and drawn at true size (the old 256-px-tile formula drew them at half size), and the canvas is DPR-aware. Verified in headless Chromium: all 4 datasets load, no console errors. New test: `tests/test_export_binary.py`. Pipeline not re-run end-to-end (needs ~GB of DEM downloads).

- 2026-09-24 UTC: 10m end-to-end validation of the §1 fixes (prepare + dinf10m + d810m, run from a snapshot so phase-2 edits couldn't leak in): 7 min, 370 s of it downloading 2.8 GB of 10m tiles; peak RSS 1.3 GB. All new checks ran and passed. The contributing area came out at 39.9 km² vs the published 42.2 km². Rerunning with only the tiles published by 2025-08 reproduced the published area exactly (422,220 cells), so the difference is entirely USGS's 2026-06-10 / 2026-09-15 10m updates. The lost area is one contiguous 2.5 km² patch on the fan (250–540 m). Published data left on the May-era build; tile provenance isn't recorded yet (see REFACTOR_PLAN §3.7).
- 2026-09-24 UTC: Phase 2 (REFACTOR_PLAN §3.1–3.5). `deliverable/` → `floodflow/` (git mv) with `pyproject.toml` (py3dep dropped; shapely/pyproj declared; pins + rationale moved from requirements.txt) and a `floodflow` console script / `python -m floodflow`. Module globals replaced by `config.Layout` + `config.BuildParams`; `cli.py` split from `pipeline.py`; binary format + manifest moved to `publish.py`; direction tables moved to `encoding.py` (verify.py no longer imports from reachability; upstream.py no longer keeps its own copy). Reachability moved to `floodflow/experimental/` (kept at the user's request). Published data moved to `docs/data/<parcel>/` + `docs/data/manifest.json` (replaces build_params.json); the explorer discovers parcels/datasets/layers from the manifest and shows a parcel picker when more than one parcel is published. Tests: pytest, 38 tests (encoding vs pyflwdir's own table, upstream trace, export round-trip, manifest, build cache, synthetic-DEM WBT end-to-end); deliberately breaking the LUT or the D∞ trace makes them fail. Added ruff + GitHub Actions CI (simulated locally in a fresh 3.12 venv: pass; not yet run on GitHub). The refactored pipeline reproduces the phase-1 10m binaries byte-for-byte (temp root, 61 s with cached tiles).
- 2026-09-24 UTC: Replaced the GitHub Actions workflow with a versioned local hook (`.githooks/pre-commit`: ruff + pytest; `git config core.hooksPath .githooks`). Added DEM provenance: `fetch` writes a `<dem>.tiles.json` sidecar, and the manifest records it per dataset (`dem`) and for the contributing area (`contributing_area_dem`).
- 2026-09-24 UTC: Regenerated all four country-club datasets on current TNM tiles (`floodflow clean`, then prepare → dinf10m → d810m → dinf1m → d81m): 4 m 43 s total, peak RSS 3.1 GB (d81m), lowest free RAM 1.4 GB, no swap, 0 verification violations. Contributing area 39.91 km² (was 42.22). Stream cells: D∞ 10m 24,511 (was 27,887), D8 10m 17,410 (19,922), D∞ 1m 2,378,964 (2,513,977), D8 1m 1,977,565 (2,105,544). The inputs include four new 1m tiles (CA_SanDiegoCo_D24 lidar, x54–55 y369–370) and the 2026-06/09 10m updates. Explorer checked in headless Chromium: all datasets load, no errors.
- 2026-09-24 UTC: The pre-commit hook caught an intermittent WBT 2.3.6 `FillDepressions` panic (`fill_depressions.rs:368`, exit 101, 1–6% of runs on identical input). The `whitebox` wrapper ignores exit codes and, with verbose off, drops error output, so it surfaced only as "output not found". `preprocess.py` now retries up to 3 times (synthetic test 0/40 failures, was ~1/20). Also fixed `.gitignore`: `data/` matched `docs/data/`; now `/data/`.
- 2026-09-24 UTC: §2 simplification. `floodflow/wbt.py` replaces the whitebox wrapper's `run_tool` (checks exit code + output, retries panics). This fixed the D8 `wbt` backend, which passed the DEM as the pointer; it now matches pyflwdir exactly. `geo.polygon_mask` unions all features (two call sites used only the first). preprocess cleanup. HUC-12/FEMA fetchers moved into the CLI, writing to docs/data + manifest layers. The FEMA dry run shows 49 vs 50 zones: the missing one is at the 8 km radius edge, probably a query-centre artifact (published file queried around De Anza Villas); verify before `--write`.
- 2026-09-24 UTC: De Anza Villas published (contributing area 0.92 km², entirely inside the Country Club's; 78% in FEMA Zone A). FEMA 49-vs-50 confirmed as a query-centre artifact (a Villas-centred query matches the published file byte for byte); the fetcher now centres on the Villas.
- 2026-09-24 UTC: Explorer rebuilt on deck.gl 9.4.0 (binary attributes, LNGLAT_OFFSETS, GPU threshold filter, GridCellLayer squares ≥2 px, dots below), lazy loading, About panel, legend ramp, URL hash, phone layout, SRI-pinned CDNs. Fixed a layer-id collision found in testing (dots→squares reused an id across classes). Not tested on a real GPU.
- 2026-09-24 UTC: Deploy branch: `floodflow publish` writes a parentless `gh-pages` commit with the manifest's files; `main` stops tracking `.bin` and they were stripped from this branch's unpushed commits (backup ref `backup/before-bin-strip`). Nothing pushed.
- 2026-09-24 UTC: Dead code/artifact cleanup after the user verified the preview on a laptop. Removed `floodflow/watershed.py`, `streams.export_geojson`, `scripts/fetch_parcel_*.py` (covered by `floodflow prepare`), the unused `docs/data/dri_2015_fan_zones.geojson`, the unreferenced `data/raw/dem/deanza_villas_2km_1m_dem.tif` (65 MB), the duplicate `data/raw/fema/` copy, dead `.claude/settings.json` allow entries, and ~2.8 GB of untracked old-pipeline outputs in `data/derived/{henderson,2km_aoi,watershed,vectors}` plus a duplicate DRI PDF. Condensed pre-rework DEVLOG entries (full text: `git show d77ea00:DEVLOG.md`).
- 2026-09-24 UTC: Go-live: refactor branch fast-forwarded into main; `floodflow publish --push` pushed gh-pages (16 files, 54.8 MB). Pages source switch to gh-pages done in repo settings (gh CLI not authenticated here). Development now happens directly on main.
