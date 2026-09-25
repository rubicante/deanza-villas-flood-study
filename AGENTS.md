# AGENTS.md

Fast entry point for agents working in this repository.

See [README.md](README.md) for project overview, layout, quickstart, and parcel list.

## Adding a new parcel

Implement a generator in `floodflow/parcels.py` with signature
`(output: Path) -> Path`, add a `Parcel` to `PARCELS` in `floodflow/config.py`,
then run `floodflow all --parcel <key>`.

## Planning workflow

- `TODO.md` — queued or pending work for the current effort
- `DEVLOG.md` — what actually happened, with short timestamped notes

Operating rules:
- Put requested future work into `TODO.md` as a checklist or ordered backlog.
- Re-read `TODO.md` before starting a new round of work so queued items stay in view.
- When the user asks for the same work again, use `TODO.md` to reconcile what is already queued instead of duplicating tasks.
- Mark items `in_progress` while working on them. When done, remove them from `TODO.md` entirely — `DEVLOG.md` is the record of what was completed and when.
- Treat one-off migration or cleanup plans as temporary; retire them when the work is done.
- If the active work changes something material, append a short timestamped note to `DEVLOG.md`.
- Before forming a hypothesis about why an external tool is producing wrong output, stratify the observed disagreements by relevant terrain/data covariates and check whether the failure pattern is uniform (suggesting your code) or clustered (suggesting a real edge case).

## Key conventions

- Run = `Layout` (paths for one parcel) + `BuildParams` (one dataset), both in
  `floodflow/config.py`. No module-level mutable state; the CLI (`cli.py`) and
  library callers go through the same `prepare(layout)` / `build(layout, params)`.
- Everything the explorer reads is owned by `floodflow/publish.py`: binary
  format v2 (drainage area in m², float32 offsets from a float64 origin) and
  `docs/data/manifest.json`. `build()` skips only when the manifest's recorded
  `params` equal the requested ones (`null` never matches).
- Derived outputs: `data/derived/runs/<parcel>/`. Published: `docs/data/<parcel>/`.
  `docs/data/**/*.bin` is gitignored on `main`; the binaries ship only on the
  one-commit `gh-pages` branch built by `floodflow publish` (`floodflow/deploy.py`).
  Development happens directly on `main` (personal project). `floodflow publish
  --push` updates the live site (GitHub Pages serves `gh-pages`).
- Explorer (`docs/index.html`): MapLibre 4.7.1 + deck.gl 9.4.0, pinned with SRI.
  If you bump a version, recompute the `integrity` hashes. Stream layers need
  distinct ids per layer class (deck.gl matches layers by id).
  The `layers` section of the manifest (HUC-12, FEMA) is hand-maintained.
- Direction tables (WBT D8 codes, D∞ neighbours, WBT→pyflwdir LUT) live only
  in `floodflow/encoding.py`; `tests/test_encoding.py` checks them against pyflwdir.
- `floodflow/experimental/` is optional analysis (reachability). Core code must
  not import from it except behind `--reachability`.
- CRS: EPSG:5070 (Albers Equal Area) throughout; EPSG:4326 for GeoJSON output
- DEM tiles are cached in `data/raw/dem/tiles/` — never deleted by `clean`
- Raw vector inputs live in `data/raw/vectors/` — never deleted by `clean`
- `prepare()` generates the parcel boundary if it is missing
- TNM always serves the newest DEM surveys, so results can drift when USGS
  publishes new tiles (2026-06/09 10m updates shrank the country-club
  contributing area from 42.2 to 39.9 km²). Tile provenance is not yet recorded.
- Tests: `pytest` (fast; `-m "not wbt"` skips the WhiteboxTools run). Lint: `ruff check .`
  Both run in `.githooks/pre-commit` (`git config core.hooksPath .githooks`). No CI by choice.

## Known non-obvious invariants (hard-won)

### D∞ accumulation: always pass `out_type="cells"`
WBT `d_inf_flow_accumulation` defaults to SCA (specific catchment area, m²/m),
not cell count. On fan terrain, noisy flow angles → contour width → 0 →
division overflow → inf. Always pass `out_type="cells"`. `verify_accumulation()`
catches SCA mode: `nonzero_min == cell_width_in_meters` means you're in SCA mode.

### WBT version: the binary is downloaded, not pinned
`whitebox==2.3.6` is the Python wrapper, which is the latest on PyPI. On first
use it downloads the WhiteboxTools binary, v2.4.0 (May 2024, the latest
open-source release). `whitebox_tools --version` shows it. A fresh install
could fetch a different binary. The tests (encoding, synthetic DEM, WBT
runner) are the check.

### WBT D8 accumulation hangs on WBT 2.4.0
`d8_flow_accumulation` runs indefinitely on large rasters. Cause unknown — not
memory, not nodata, not cycles. Fix: compute pointer with WBT, accumulate with
`pyflwdir.from_array(ptr, ftype='d8', check_ftype=False)`. If upgrading WBT,
retest D8 accumulation before removing the `wbt_ptr_pyflwdir` backend.

### Never use `pyflwdir.from_dem` — use `from_array` with WBT pointer
`from_dem` refills depressions using Wang & Liu 2006, connecting sub-basins
that WBT's breaching keeps separate. Produces accumulation ~3.37× higher than
D∞. Always use `from_array` with a WBT-computed pointer.

### Mask D8 pointer nodata to 0 before pyflwdir
WBT writes nodata as -32768 (int16). pyflwdir treats -32768 as a flow
direction and corrupts accumulation. `d8.py` masks automatically:
`ptr_data[~valid_mask] = 0`.

### `rasterio.warp.transform` returns lists, not arrays
Indexing Python lists with boolean masks or argsort produces wrong results
silently. Always wrap: `lons = np.asarray(lons)`. `publish.export_binary()` does this.

### `features.shapes` / `features.rasterize` require int16 value + uint8 mask
Passing uint8 for both corrupts edge cells by 1-2 pixels. Cast value array to
int16, mask to uint8. Affects pour-point rasterization and polygonization in
`upstream.py`.

### WBT paths must be absolute
WBT silently produces no output for relative paths. Always pass
`str(Path(p).resolve())`. The library does this internally.

### Breach then fill, not fill-only, for alluvial fan terrain
Fill-only creates artificial flats that block D8 routing. On steep canyon
terrain, fill-only produced 0% FEMA hazard overlap; breach+fill produced 72%.
`preprocess_dem()` defaults to `breach_then_fill`.

### All overlapping 1m tile surveys must be fetched, not just the newest
TNM returns multiple surveys per grid position. "CaliforniaGaps" tiles have
holes in steep terrain (canyons). `_query_tnm` returns all surveys
newest-first; `rio_merge(method='first')` uses newest where available and
falls back to older surveys to fill gaps. Do not re-introduce per-position
deduplication.

### Reachability filter is wrong for alluvial fan terrain
D8/D∞ pointers on nearly flat fan terrain route flow arbitrarily and often
miss the parcel polygon entirely. Default `reachability_mode='none'` — export
all streams within the CA. Use `--reachability boolean` only when the parcel
sits in a clear channel, not on a fan.

### WBT fill_depressions writes float64 uncompressed
Output is ~3× larger than expected. `compute_dinf()` recompresses to
float32+LZW after WBT writes.

### WBT 2.4.0 FillDepressions panics intermittently; the wrapper hides it
About 1–6% of runs on identical input panic (`fill_depressions.rs:368`,
exit 101) and write no output. The `whitebox` Python wrapper never checks the
exit code, and with verbose off it drops all output, errors included, so this
looks like success. `preprocess.py` retries when the output is missing. Other
WBT calls only check that the output exists; they don't retry.

### 2D rain-on-grid: raw DEM, and a flow-speed time step
`floodflow flood` models on the raw lidar, never the breached/filled DEM:
in 2D, depressions are real storage. The local-inertial solver
(`hydraulics.py`) sets Δt from the *face* flow speed, |q|/h_f + √(g h_f),
with CFL 0.3. Don't go back to the textbook gravity-wave Δt (√(g h_max)):
steep canyon and sheet flow is supercritical and went unstable with it,
and the Froude cap (Fr ≤ 1) that hid this slowed 30% slopes ~1.5× and
lowered the Villas' depths ~10%. Divide face discharge by *face* depth,
never by the receiving cell's depth: a channel spilling onto a 1 mm film
otherwise reads as 100 m/s (this collapsed Δt and polluted max speed).
The domain is traced upstream of parcel ⊕ 300 m, not buffered from the
parcel's own contributing area (a wash from outside that area floods the
Villas' east side).

### `floodflow flood --remote`: Modal, and keep `floodflow/__init__` lazy
`--remote [CPUS]` runs only the solver on a temporary Modal machine
(`floodflow/remote.py`; tokens from `.env`: MODAL_TOKEN_ID/SECRET; `pip install
.[remote]`). The remote image has only numpy + numba, and Modal imports
`floodflow.remote` there, so `floodflow/__init__.py` must stay lazy (PEP 562):
an eager import of d8/fetch/etc. fails remotely with "No module named rasterio".
The 4 m Villas run on 64 cores matches the local run bit for bit (97 s vs 466 s).
A crash while Modal imports the module makes the client retry forever: Ctrl-C it.

### LISFLOOD-FP 8 cross-check: only its diffusive solver is usable here
Built locally (not a dependency): `~/.local/src/lisflood/bin/lisflood`
(Zenodo 13121102, "v8.2" archive that reports 8.1.0; CPU, double, NetCDF
from Debian packages extracted to `deps/root`, no root install).
The solver is picked by keyword: none = diffusive (adaptive Δt), `acceleration`
= ACC (local inertial), `fv1` = full SWE. On the tilted-plane tests
(2/10/30%) the diffusive solver matches ours and the kinematic wave. ACC
matches at 2% and 10% but loses ~90% of its water at 30%, and on the Villas
4 m domain it goes unstable ~10 min into the storm (volume 2.5× rain by
14 min), CFL 0.3 included. `max_Froude` is only read by the sub-grid-channel
(SGC) solver; plain ACC ignores it. The diffusive solver is stable on the
Villas domain but its Δt falls below 0.01 s as depths grow (hours+ at 4 m).
At 8 m it reached 45 min in 69 min wall and agrees with ours (DEVLOG 2026-09-25).
FV1 is off by 20% at 2% slope (2 m cells) and slow on steep slopes. FV1 takes
rain only as NetCDF (`dynamicrainfile`), and its reader treats dimension ids
as variable ids: define variables in dimension order (time, y, x). scipy
reorders them. For a domain edge that drains, set `nodata_elevation` below the
terrain and add `drain_nodata` (not supported by SGC).

### WBT set_verbose_mode(False) prevents pipe stalls
On large rasters, WBT progress output fills the pipe buffer and stalls the
parent. Always call `set_verbose_mode(False)`.
