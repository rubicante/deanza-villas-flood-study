# TODO.md

Use this file as the queued-pending work list for the current effort.

Suggested format:
- Keep items short and ordered by priority.
- Use checkboxes or a simple backlog list.
- Mark items `in_progress` while working on them. When done, remove them — DEVLOG.md records the outcome.
- Add or reconcile items when the same request comes up again.

Recommended relationship to other repo logs:
- `DEVLOG.md` = what actually happened, with short timestamped notes
- `TODO.md` = what is queued or pending (not an archive of completed work)

## Backlog (existing)

### Tier 2 — remaining

- [ ] [MANUAL DOWNLOAD REQUIRED] Download full California NFHL state file geodatabase from FEMA MSC (https://msc.fema.gov/portal/advanceSearch → California → "NFHL Data-State"). This contains the complete unfiltered NFHL including Zone D, Zone X minimal hazard, and all ancillary layers not in the reduced set. FEMA updates state extracts every two weeks. The MSC portal has TLS cipher-suite restrictions that block automated download from this server — must be done in a browser. Extract the Borrego panels (DFIRM 06073C) and save as `data/raw/fema/nfhl_ca_full_borrego.gpkg` (or similar). This is additive to the reduced-set fetch above; not blocking.

### Tier 3 — Additional diagnostic terrain metrics

Tier 3 complete. Profile curvature/TPI, HAND relative-position metrics, and DRI active-fan roughness comparison have been run and synthesized; completion details are recorded in `DEVLOG.md`.

### Tier 4 — Dependency hygiene

- [ ] py3dep 0.19.0 retained (not removed). The Eastern SD 2017 QL2 lidar tiles don't cover the parcel; py3dep WCS mosaic is the correct DEM source. The known 0.19.0 non-square pixel regression (GitHub #77) is worked around by reprojecting py3dep output to exactly 1m square pixels in EPSG:5070 via rasterio. Option: pin py3dep once a fixed version is released.

## Plan 2 — Reproducibility in Code

Implementation order: documentation first, then fetch scripts, then regenerate.py.

- [x] `data/raw/manual/PROVENANCE.md` — document one-off artifact origins (DRI digitization, SanGIS parcels, FEMA fetch, HUC-12, reference PDFs, community bbox, AOI buffers)
- [x] `scripts/fetch_fema.py` — ArcGIS REST query for DFIRM 06073C → `data/raw/fema/nfhl_borrego_valley.geojson`
- [ ] `scripts/fetch_huc12.py` — USGS NLDI API call for HUC-12 181002030302 → `data/derived/vectors/borrego_palm_canyon_huc12.geojson`
- [x] `scripts/build_aois.py` — parcel buffer → derived AOIs (2km, 8km) → `data/derived/vectors/`
- [ ] `scripts/regenerate.py` — smoke test: regenerates all canonical artifacts from raw sources and diffs against committed versions
- [ ] Satellite validation regeneration — stalled on Earthaccess auth (no EDL credentials in this environment). Outputs (`satellite_validation.html`, `.md`) are known-stale with old parcel boundary and old FEMA. Needs `.netrc` or EARTHDATA_USERNAME/EARTHDATA_PASSWORD to re-run.
