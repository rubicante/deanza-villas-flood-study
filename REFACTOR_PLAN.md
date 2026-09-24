# Refactoring Plan (preliminary)

Drafted 2026-09-24 after a read-through of the repo as of `195ce77`. This is a
first pass. Items are grouped by theme and roughly ordered by priority inside
each group. File references point at the code as it stands today.

## Progress

### Phase 1: §1 correctness fixes — done 2026-09-24
Items 1.1–1.12, plus 1.13 found along the way. Details are in the §1 status
column and in `DEVLOG.md`.

**10m end-to-end validation** (`prepare`, `dinf10m`, `d810m`) ran in 7 min,
mostly downloading. Every new check ran and passed. The run turned up one real
finding: **USGS's 2026-06 and 2026-09 10m DEM updates shrink the country-club
contributing area from 42.2 to 39.9 km²** (a single 2.5 km² patch on the fan).
With the pre-May tiles, the current code reproduces the published area exactly,
so the change comes from the data, not the code. The published data is still
the May-era build (see 3.7).

### Phase 2: §3 foundation — done 2026-09-24
- **3.1** ✅ `floodflow` package with `pyproject.toml` and a `floodflow` CLI
  (`python -m floodflow` also works). `py3dep` is dropped, `shapely` and
  `pyproj` are declared, and the version-pin rationale is kept. No lockfile
  yet (`uv lock` is a one-liner when wanted).
- **3.2** ✅ `config.Layout` plus `config.BuildParams` replace the module
  globals. `cli.py` is split from `pipeline.py`.
- **3.3** ✅ Published data lives in `docs/data/<parcel>/`, and
  `docs/data/manifest.json` replaces `build_params.json`. The explorer finds
  parcels, datasets, and layers through the manifest and shows a parcel picker
  when more than one parcel is published (tested in headless Chromium with 1
  and 2 parcels).
- **3.4** ✅ pytest suite, 38 tests, about 2 s, including a synthetic-DEM run
  through real WBT and pyflwdir. Deliberately breaking the lookup table or the
  D∞ trace makes the tests fail.
- **3.5** ✅ (changed) ruff plus pytest now run from a **local pre-commit hook**
  (`.githooks/pre-commit`, enabled with `git config core.hooksPath .githooks`)
  instead of GitHub Actions. That's enough for a solo project with a 2 s suite.
  What CI would add is a clean environment. To get that locally, occasionally
  run the tests in a throwaway venv (`uv venv /tmp/x && uv pip install -e ".[dev]"`).
- **3.6** ⏸ Not done. The 10m BFS took only 2 s (399K cells), so this is lower
  priority than I assumed. It would matter only for a 1m contributing area.

Also done along the way:
- **2.3** ✅ Reachability moved to `floodflow/experimental/` (kept at your
  request).
- **Shared direction tables:** `floodflow/encoding.py` now holds the D8, D∞,
  and lookup tables. `verify.py` no longer imports from reachability, and
  `upstream.py` no longer keeps its own copy.
- **4.5 (partial):** dataset buttons use CSS classes with `aria-pressed`.
- **Check:** the refactored pipeline reproduces the phase-1 10m binaries
  byte for byte.

### Regeneration — done 2026-09-24
All four datasets were rebuilt on current (2026) TNM tiles, with provenance
recorded in the manifest. The contributing area is now 39.91 km², and stream
cells dropped 5–12%. The inputs include new San Diego County 2024 lidar
(four 1m tiles published 2026-09-15). The run took 4 m 43 s, with 3.1 GB peak
memory. The 1m out-of-memory risk didn't materialise.

### Found while committing
The first commit attempt was blocked by the new pre-commit hook: the synthetic
WBT test failed. That turned out to be a real WBT 2.3.6 bug. `FillDepressions`
intermittently panics (exit 101), and the `whitebox` wrapper ignores exit
codes and, with verbose off, error output too. The failure rate was 1–6% on
identical input.
- `preprocess.py` now retries a missing output (0 failures in 40 test runs,
  against about 1 in 20 before).
- 2.4's shared WBT helper should check real exit codes for every tool, not
  just whether the output file exists.

Also, `.gitignore`'s `data/` rule was ignoring `docs/data/`, so the new site
data would never have been committed. It's anchored to `/data/` now.

### Phase 3: §2 simplification — done 2026-09-24 (deletions on hold)
- **2.4** ✅ `floodflow/wbt.py` calls the WBT binary directly: it checks the
  exit code *and* the output file, and retries only panics (exit 101). It
  replaces the wrapper's `run_tool` everywhere, which also fixed the opt-in
  D8 `wbt` backend: that call had been passing the DEM as the pointer. That
  backend now matches pyflwdir exactly on the synthetic grid. Tested with a
  fake WBT binary covering the success, panic-retry, persistent-panic,
  exit-0-without-output, and non-panic-error cases.
- **2.5** ✅ `preprocess.py`: removed the dead branch, deleted the
  intermediate breached DEM, and fixed the breach log, which now reports
  max cut, max fill, and a signed net volume.
- **2.7** ✅ `geo.polygon_mask` rasterizes the *union* of all features. Two
  call sites had used only the first feature. Experimental reachability keeps
  its own copy.
- **2.8** ✅ `floodflow fetch-huc12` and `floodflow fetch-fema [--write]`
  (moved from `scripts/`) write straight to `docs/data/` and register in
  the manifest's `layers`. HUC-12 regenerates byte-identical, and the area is
  now computed instead of hardcoded (still 149.1 km²). ⚠️ The FEMA dry run
  shows 49 zones live against 50 published. The missing one is an 8.1 ha AO
  zone 7.5 km away, at the edge of the 8 km search radius. Likely cause: the
  published file was queried around De Anza Villas (then the default).
  Verify after the Villas run before writing.
- **2.1, 2.2 (rest), 2.3:** deletions are on hold. `scripts/fetch_parcel_*.py`
  (redundant with `floodflow prepare`), `watershed.py`, and
  `data/raw/fema/nfhl_borrego_valley.geojson` (a duplicate of the published
  copy) are candidates.

### Phase 4: De Anza Villas + §4 explorer — done 2026-09-24
- **De Anza Villas** is published alongside the Country Club (the default).
  Its contributing area is only **0.92 km²**: a small mountain-front
  catchment, and one that lies entirely inside the Country Club's 39.9 km².
  **78% of the Villas is in FEMA Zone A** (a Special Flood Hazard Area; no
  base flood depth set). The Country Club's zones are AO with 1–2 ft depths.
  The About panel explains why a small traced area doesn't mean low risk.
- **FEMA 49-vs-50 resolved:** a query centred on the Villas returns the
  published 50 zones byte for byte. It was a query-centre artifact, so the
  fetcher now centres on the Villas.
- **4.1** ✅ deck.gl 9.4.0 (575 KB gzipped, not the ~300 KB I guessed
  earlier) with binary attributes read straight from the v2 buffer and
  `LNGLAT_OFFSETS`, so there are no per-point JS objects and full precision.
  The threshold is a GPU filter (`DataFilterExtension`). Zoomed in, cells
  are exact `GridCellLayer` squares centred on the cell centre
  (`offset [0,0]`, verified in deck's source). Below 2 px per cell they're
  drawn as dots, since sub-pixel squares don't render.
- **4.2** ✅ Datasets load when selected and are cached. The first view
  downloads about 0.3 MB instead of about 55 MB.
- **4.4** ✅ An About panel in plain language (shown on first visit), a
  colour-ramp legend, and a hint when the slider is above anything that
  drains to the property.
- **4.5** ✅ MapLibre 4.7.1 and deck.gl pinned on jsdelivr with SRI hashes
  (checked against the npm tarball). Shareable URL hash
  (`#parcel=…&ds=…&t=…&view=…`). Phone layout tested at 390 px.
- **4.6** ✅ Title "De Anza Flood Explorer"; the parcel picker offers both
  properties.
- Tested in headless Chromium with software WebGL: every dataset for both
  parcels, the slider, parcel switching, link restore, and phone layout.
  Found and fixed a deck.gl layer-id collision on the dots→squares switch.
  Known and harmless: luma.gl logs one "layout for attribute positions/normals"
  warning for GridCellLayer with binary data (reproduced in isolation).
  ⚠️ **Not tested on a real GPU or phone.** Try it on yours before go-live.

### Phase 5: #4c deploy branch — done 2026-09-24 (not pushed)
- `floodflow publish` builds a **one-commit `gh-pages`** branch with
  `index.html`, the manifest, and exactly the files it references. It uses a
  temporary index, so the working tree and current branch aren't touched.
  `--push` force-pushes it; not run.
- `main` no longer tracks `docs/data/**/*.bin`. They were also stripped from
  this branch's unpushed commits, so merging adds no binaries to `main`'s
  history. A backup ref `backup/before-bin-strip` keeps the pre-strip
  commits until you delete it.
- **Go-live checklist:**
  1. Merge the branch into `main` and push.
  2. `floodflow publish --push`.
  3. In GitHub → Settings → Pages, set the source to branch `gh-pages`,
     folder `/ (root)`.
  4. Open the site on your phone.

### Phase 6: deletions + git cleanup — done 2026-09-24 (after laptop check)
- **Dead code:** `floodflow/watershed.py`, `streams.export_geojson`,
  `scripts/fetch_parcel_*.py`.
- **Dead artifacts:** the unused DRI fan-zones layer, the unreferenced 65 MB
  DEM, the duplicate FEMA copy, dead `.claude/settings.json` entries, a
  duplicate DRI PDF, and about 2.8 GB of old-pipeline outputs in
  `data/derived/`.
- **DEVLOG:** condensed to the findings still worth keeping. The full text is
  at `git show d77ea00:DEVLOG.md`.
- **git:** removed the backup refs and ran `git gc`. The three unreachable
  May-7 commits were checked first: a raster-laden duplicate of `b61e234`,
  plus a dropped stash of old AOI edits.

### Still open
- **Misleading breach log.** `preprocess.py` logs "M m³ removed" as a negative
  number, because WBT `breach_depressions` also fills what it can't breach.
  The number is real; the label is wrong. On the 25 km bootstrap it reports
  1.2 km³ of net fill, presumably around the closed Borrego Sink basin. That's
  worth a look, though it's outside the contributing area.

## TL;DR

The core hydrology (fetch → breach/fill → D8/D∞ → contributing area → stream
threshold) is sound, and the hard-won invariants in `AGENTS.md` are real and
worth keeping. The problems sit around that core:

1. **A few real bugs.** The worst one is that switching parcels or changing
   the threshold silently reuses stale outputs.
2. **The 1m and 10m datasets aren't comparable in the explorer.** The slider
   counts cells, and a cell at 10m covers 100× the ground of a cell at 1m.
3. **About 40% of the Python is dead or optional code** (`watershed.py`,
   most of `reachability.py`, three of the four D8 backends, `export_geojson`).
4. **The explorer does too much work on the CPU.** It downloads ~56 MB before
   the map appears and calls `map.project()` on up to 2.5M points every frame.
5. **The repo is 3.3 GB on disk when the actual content is about 30 MB.** Most
   of it is git garbage and stale `data/derived/` output from an earlier
   pipeline, and the docs describe files that no longer exist.

---

## 1. Correctness fixes (do first)

| # | Where | Problem | Fix | Status |
|---|---|---|---|---|
| 1.1 | `_pipeline.py` `build()` | `if binary.exists(): return` caches on the output filename only. Changing `--threshold`, `--threshold-frac`, `--hydro`, or `--parcel` does nothing unless you run `clean` first. `dem_{res}_filled.tif` is cached the same way and ignores `--hydro`. | Namespace every derived path by parcel key, and put the parameters in the names (or in a small `params.json` sidecar that gets compared on each run). Rebuild when anything differs. | ✅ Paths under `data/derived/runs/<parcel>/`; `docs/build_params.json` compared before skipping; filled DEM name includes the hydro strategy; streams path computed *after* `--threshold-frac` is converted (it used the pre-conversion value before). Cache logic tested with stubs. |
| 1.2 | `_pipeline.py` `prepare()` + `all` | `all` calls `prepare()` without `parcel_fn`, so `all --parcel deanza_villas` fails on a fresh checkout, even though the README documents that exact command. If a contributing area from another parcel already exists, `all` reuses it silently. | Pass `parcel_fn` through. Key `CONTRIBUTING_AREA` by parcel (see 1.1). | ✅ `all` passes `parcel_fn`; `prepare()` republishes the parcel and contributing-area layers to `docs/` even when cached. |
| 1.3 | `_pipeline.py` `_export_binary()` | The top-10 "inside boundary" sanity check reprojects to EPSG:4326 and then calls `.buffer(10)`. That buffers by **10 degrees**, so the check can never fail. | Buffer in EPSG:5070 before reprojecting, or test in 5070 directly. | ✅ Buffer in EPSG:5070. The test confirms the check now fires. |
| 1.4 | Explorer, cell units | The threshold is in cells. 250 cells at 1m is 250 m²; at 10m it's 25,000 m². Switching datasets at the same slider position compares networks at 100× different drainage areas, which undercuts the "compare algorithms and resolutions" purpose of the page. | Export drainage **area** (m²), i.e. cells × res², and label the slider in m² / ha / km². | ✅ Binary v2 stores m². Slider runs 250 m² → 10 km², ticks placed on the log scale (the old evenly spaced ticks were off), default 10 ha. |
| 1.5 | Explorer `init()` | "Stream cells" on load shows the D∞ **1m** count (2.5M) while the active dataset is D∞ **10m** (27.9K). The HTML starts the slider at 5,000, then JS resets it to 1,000. | Derive both from `activeDs` and one default constant. | ✅ |
| 1.6 | Explorer `renderCells()` | Each cell is drawn from `floor(project(center))` toward the lower right, which shifts every cell half a cell to the SE (5 m at 10m). The canvas also ignores `devicePixelRatio`, so it's blurry on HiDPI screens. | Center the square on the point and scale the canvas by DPR. Moot if 4.1 lands. | ✅ Squares centred on points; DPR-aware canvas that resizes only when its size changes. |
| 1.7 | `fetch.py` `_download_tile()` | A tile counts as cached if it's larger than 100 KB, so an interrupted download becomes a permanently corrupt cache entry. | Download to `*.part` and rename it into place when finished. Optionally check `Content-Length`. | ✅ `.part` + rename, plus a `Content-Length` check. |
| 1.8 | `fetch.py` `_query_tnm()` | `max: 100` with no pagination. Because we now fetch every overlapping survey per tile position (on purpose), a larger area can exceed 100 results and get truncated without any warning. | Page through results using `offset`/`total`, or raise if `total > len(items)`. | ✅ Paginates with `offset`; raises if short. Live test: 119 tiles for the 25 km extent (previously truncated at 100). |
| 1.9 | `verify.py` `verify_monotonicity_along_paths()` | For D∞ it doesn't check monotonicity at all, only whether the pointer is valid. The name and docstring promise more than it does. | Implement the tolerant monotonic check the docstring describes, or rename it to `verify_pointer_validity` for D∞. | ✅ Implemented a real check: `accum[nbr] ≥ share × accum[cell]`. 0 violations on real WBT data, and it catches a reversed pointer. |
| 1.10 | `d8.py` | The default is `backend="auto"`, which tries WBT `d8_flow_accumulation` first. `AGENTS.md` says that call hangs forever on WBT 2.3.6. The `pyflwdir` backend uses `from_dem`, which `AGENTS.md` says never to use. | Keep only `wbt_ptr_pyflwdir` (see 2.2). | ✅ Default `wbt_ptr_pyflwdir`; `auto` and `pyflwdir` removed; `wbt` kept as opt-in for retesting after a WBT upgrade. |
| 1.11 | `_pipeline.py` `build()` signature | The function default is `reachability_mode="boolean"`, but the CLI default is `"none"`, and `AGENTS.md` says `none` is correct for fan terrain. Calling `build()` as a library function gives different results from the CLI. | Make `"none"` the single default. | ✅ |
| 1.12 | Binary lon/lat precision | lon/lat are stored as absolute float32, which gives about 0.7 m × 0.4 m quantization at this latitude. That's close enough to 1m cells to produce visible jitter or moiré at max zoom. | Store float32 offsets from an origin written in the header, or store integer cell indices plus a transform (see 4.3). | ✅ In the exporter (float64 origin + float32 offsets, ~1 mm). ⚠️ The published files were migrated, not regenerated, so they keep v1 precision until the next run. |
| 1.13 | Explorer cell size (found during 1.6) | The formula `156543 · cos φ / 2^z` assumes 256 px tiles, but MapLibre zoom uses 512 px tiles, so every cell was drawn at **half** its ground size. | Measure pixels per cell by projecting a cell-height offset. | ✅ Measured 0.61 px per 10 m at the default zoom, vs 0.30 px from the old formula. |

## 2. Simplification

2.1 **Delete dead modules.** Nothing imports `deliverable/watershed.py` (288
lines). `streams.export_geojson` is unused. Git history keeps them if we need
them back.

2.2 **Collapse `d8.py` to one backend** (WBT pointer → LUT → `pyflwdir.from_array`),
from 204 lines to about 60. Keep the invariant comments.

2.3 **Decide what to do with reachability.** `reachability.py` is 644 lines and
is off by default because `AGENTS.md` calls it wrong for fans. It also carries
the only tests in the repo. Options: (a) move it under `deliverable/experimental/`
with its tests, or (b) delete it and keep a DEVLOG pointer. I lean toward (a),
since the flow-weighted work is interesting for future study.

2.4 **Share one WBT helper.** Five modules each repeat
`WhiteboxTools(); set_working_dir; set_verbose_mode(False)` plus
"resolve paths, run, check the output exists". A `_wbt.run(tool, **paths)` helper
would enforce the absolute-path, quiet-mode, and output-exists invariants in one
place.

2.5 **Clean up `preprocess.py`.** It has a dead `if/else` (both branches set
`filled_out = output`), leaves `_breached.tif` behind, and reads the full raster
twice just to print diagnostics.

2.6 **Vectorize `_export_binary`.** It calls `struct.pack` 2.5M times in Python.
Build a single numpy structured array and call `.tofile()`, which should be about
100× faster.

2.7 **Remove duplicated raster masking.** `_mask_to_boundary`, `d8.py`
(watershed_geom), and `reachability._rasterize_target` each rasterize a polygon
their own way. Replace them with one `rasterize_mask(geom, like=raster)`.

2.8 **Merge the fetch scripts into the CLI.** `scripts/fetch_parcel_*.py` are
14-line wrappers. `fetch_huc12.py` and `fetch_fema.py` write to places the
explorer doesn't read (`data/derived/vectors`, which `clean` wipes, and
`data/raw/fema`), so someone has to copy the files into `docs/` by hand, and
that step isn't documented. Make them pipeline subcommands (`fetch-huc12`,
`fetch-fema`) that write straight to the published data directory. Also:
`fetch_fema.py` hardcodes the country-club parcel, and `fetch_huc12.py`
hardcodes `area_km2: 149.1` instead of computing it.

## 3. Foundation

3.1 **Packaging.** Add a `pyproject.toml` with a `[project.scripts]` entry, pin
dependencies in a lockfile (`uv lock`), and give the package a real name
(`deliverable/` → e.g. `borrego_flow/`) with a `__main__.py` instead of
`python -m deliverable._pipeline`. `requirements.txt` pins `py3dep==0.19.0` even
though nothing imports it any more (`fetch.py` calls TNM directly). Drop it and
list `shapely` and `pyproj` explicitly.

3.2 **Configuration instead of mutable globals.** Right now `PARCEL` and
`REACHABILITY_TARGET` are reassigned inside `if __name__ == "__main__"`, so the
module behaves differently when imported than when run. Replace them with a
`Run` dataclass (parcel key, resolution, algorithm, threshold, hydro strategy)
that produces every path. This is the structural fix behind 1.1 and 1.2.

3.3 **Output layout per parcel.** Use `data/derived/<parcel>/…` and
`docs/data/<parcel>/…`, with a `docs/data/manifest.json` listing the parcels,
datasets, units, and build parameters. That lets the explorer offer a parcel
picker (De Anza Villas *and* the country club) without code changes.

3.4 **Tests.** Move to `pytest`. The highest-value additions, in order:
- `upstream._neighbors_flowing_into` on hand-built angle grids (0°, 45°, 359.9°,
  360°, -1). This function defines the contributing area for everything
  downstream of it.
- A `_WBT_TO_PYFLWDIR` LUT round-trip test against `_D8_DELTA`.
- A binary export → parse round-trip test using the same header layout the JS
  reads.
- One tiny synthetic-DEM end-to-end run (a tilted plane with a notch) that
  asserts the outlet accumulation, so we notice if WBT or pyflwdir upgrades
  change behavior. `requirements.txt` already asks for exactly this.

3.5 **CI.** A GitHub Action that runs ruff and pytest (WBT downloads its binary,
so cache it). Optionally add a headless check that `docs/index.html` loads its
data without console errors.

3.7 **DEM provenance.** TNM always serves the newest surveys, so rebuilding
can change results without any code change (see Progress). Record the tile
IDs and publication dates used for each dataset in the manifest, and add an
optional `--dem-as-of YYYY-MM-DD` to reproduce an earlier build.
✅ Recording is done: each fetched DEM gets a `.tiles.json` sidecar, which is
copied into the manifest as `dem` (per dataset) and `contributing_area_dem`.
⏸ `--dem-as-of` isn't done yet (it would be a publication-date filter in
`_query_tnm`).

3.6 **Performance of the contributing-area BFS.** `upstream.py` is a pure-Python
BFS. It's fine at 10m (422K cells) but would take minutes to hours at 1m.
Vectorizing it or running it under numba (already installed via pyflwdir) is
cheap insurance for larger areas.

## 4. Website (`docs/index.html`)

4.1 **Render on the GPU.** Replace the Canvas2D loop (a `map.project()` call per
point, per frame, over up to 2.5M points) with a MapLibre custom WebGL layer or a
deck.gl `ScatterplotLayer`/`GridCellLayer`. Pass the threshold as a shader
uniform so dragging the slider doesn't touch any per-point data on the CPU. This
also removes the occupancy buffer, fixes the half-cell offset and DPR problems,
and deletes most of the render code.

4.2 **Lazy-load datasets.** Today the page downloads all four binaries
(~56 MB) one after another *before* the map initializes, although the default
view only needs the 0.3 MB D∞ 10m file. Load the active dataset first, fetch the
others on demand or in the background, and show progress per dataset.

4.3 **Binary format v2.** Version 1 has no metadata, so the JS hardcodes the
resolution and color per filename. Version 2 would put the following in the
header (or in `manifest.json`): resolution, algorithm, value units (m²),
origin, and CRS, along with quantized coordinates (see 1.12). Stay on raw typed
arrays for load speed, and gzip them (GitHub Pages serves gzip).

4.4 **Explain what the map shows.** Add a color-ramp legend (there is none now),
a short "what am I looking at" panel, and a caveat. Stream-threshold networks
are *potential flow paths*, not flood zones. On an active alluvial fan, the
County and FEMA position is that the whole fan is subject to flooding
(`data/raw/docs/manifest.md`). For a site titled "Flood Study" this caveat
matters.

4.5 **Tidy up.** Move the inline button styles into CSS classes with an
`aria-pressed` state. Pin MapLibre with SRI, or vendor it, instead of loading a
bare `unpkg` URL. Stop calling `sizeCanvas()` every frame. Add a URL hash for
dataset, threshold, and view so links are shareable. Remove the unused
`docs/dri_2015_fan_zones.geojson`, or bring the layer back deliberately.

4.6 **Title and default parcel.** The page is titled "De Anza Villas Flood
Study", but the default parcel is the De Anza Country Club. Pick one, or let
3.3 make it a picker.

## 5. Repo hygiene

5.1 **Git storage.** `.git` is 3.3 GB. `git count-objects` reports 2 GB of loose
objects and 1.2 GB of `tmp_pack_*` garbage left by interrupted operations. The
real pack is 29 MB. Running `git gc --prune=now` should recover almost all of
it. Confirm nothing uncommitted is wanted before running it.

5.2 **Tracked data vs `.gitignore`.** `.gitignore` excludes `data/`, but
`data/raw/dem/deanza_villas_2km_1m_dem.tif` (65 MB, not referenced by any code),
three PDFs, and the FEMA GeoJSON were force-added anyway. Decide on a rule:
keep the PDFs and the small vector references and add `!` exceptions for them,
and untrack the DEM. Every regeneration of `docs/*.bin` adds about 56 MB to
history. Consider publishing binaries from a GitHub Actions build artifact, or
at least keep the 1m binaries small with 4.3.

5.3 **Stale derived data.** About 2 GB in `data/derived/henderson/`,
`data/derived/2km_aoi/`, and `data/derived/watershed/` comes from the pre-May-12
pipeline. `clean` doesn't touch any of it. Delete it after a quick look.

5.4 **Docs drift.**
- `DEVLOG.md` isn't chronological (a stray `Format:` line and a `## Log` header
  sit in the middle). Most entries reference files that no longer exist
  (`spikes/`, `outputs/`, `config/study.yaml`, Henderson Canyon, SKILL.md, the
  QGIS project).
- `data/raw/docs/manifest.md` has a stale "Next step".
- `.claude/settings.json` contains an absolute path from another machine
  (`/Users/agp/...`).

Suggested fixes: collapse the pre-May-12 history into one "prior
architecture" paragraph, and keep `AGENTS.md` invariants as the durable record.

5.5 **Lint.** Add ruff to dev dependencies. It isn't installed, even though
`.claude/settings.json` allowlists it. pyflakes currently flags only an unused
`import re` in `fetch.py`.

## 6. Suggested sequencing

1. **Hygiene first (low risk, fast):** 5.1, 5.3, 2.1, 5.5. This also makes
   every later diff easier to review.
2. **Foundation:** 3.1 → 3.2/3.3 (this fixes 1.1, 1.2, and 1.11 structurally)
   → 3.4 tests in the same PRs.
3. **Pipeline correctness:** 1.3, 1.7–1.10, 1.12, 2.2–2.7, then regenerate
   every binary once.
4. **Explorer:** 1.4 + 4.3 (units and format together) → 4.1 → 4.2 → 4.4–4.6.
5. **Docs:** 5.4, and update README/AGENTS to match the new CLI.

Each step should leave the live site working. The explorer only depends on
`docs/`, so pipeline refactors can land before any website change as long as
the v1 binaries stay in place.

---

## Future areas of study
