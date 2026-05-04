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

## Backlog

### Tier 2 — remaining

- [ ] [MANUAL DOWNLOAD REQUIRED] Download full California NFHL state file geodatabase from FEMA MSC (https://msc.fema.gov/portal/advanceSearch → California → "NFHL Data-State"). This contains the complete unfiltered NFHL including Zone D, Zone X minimal hazard, and all ancillary layers not in the reduced set. FEMA updates state extracts every two weeks. The MSC portal has TLS cipher-suite restrictions that block automated download from this server — must be done in a browser. Extract the Borrego panels (DFIRM 06073C) and save as `data/raw/fema/nfhl_ca_full_borrego.gpkg` (or similar). This is additive to the reduced-set fetch above; not blocking.

### Tier 3 — Additional diagnostic terrain metrics

- [ ] Compute profile curvature (wbt.profile_curvature or equivalent) — distinguishes convex/channelized from concave/sheet-flow fan surfaces. Most diagnostic single metric for identifying active fan lobes and avulsion-prone zones.
- [ ] Compute Topographic Position Index (TPI) — reveals local high/low positions, subtle channel-levee systems, abandoned lobes, topographic traps. At 1m resolution this shows features invisible to slope alone.
- [ ] Compute HAND (Height Above Nearest Drainage) as relative position index only — use as evidence of where channel avulsion would impact the parcel, not as an inundation depth proxy. Follow FEMA alluvial fan guidance: HAND is relative terrain evidence, not primary depth indicator on active fans.
- [ ] Compare parcel-scale roughness magnitude against active/inactive fan surface benchmarks from DRI 2015 mapping. Researched: no public downloadable GIS layer exists (checked SanGIS, SANDAG, ArcGIS Online, FEMA Risk MAP). The DRI 2015 presentation PDF (https://cdn.ymaws.com/floodplain.org/resource/resmgr/2015Conference/Wednesday/Borrego-Springs-Alluvial-Fan.pdf) contains clear maps suitable for digitization. Page 20 is the best source: binary active/inactive fan areas with lat/lon graticule ticks, scale bar, and road/drainage context. Page 14 has richer geomorphic unit classes (Qa1-Qa4, Qf1a-Qf5, etc.) if age-specific comparison is needed. Digitization plan: render pages at 300-600 dpi → crop to map frame → georeference in QGIS using graticule ticks as GCPs → affine transform → digitize polygon classes → reproject to EPSG:5070. Expected confidence: moderate for broad extents and large polygons, low-moderate for small inactive polygons. Also consider contacting SanGIS/County Flood Control to request original GIS — the DRI work was contractor-produced and likely exists as CAD/GIS production data even if not publicly served. Detailed plan at kanban workspace `t_f11b4a8f`. Roughness comparison method: Frankel & Dolan 2007 — active fan lobes are rough, inactive surfaces smooth out with age (JGR Earth Surface, doi:10.1029/2006JF000644).

### Tier 4 — Dependency hygiene

- [ ] py3dep 0.19.0 retained (not removed). The Eastern SD 2017 QL2 lidar tiles don't cover the parcel; py3dep WCS mosaic is the correct DEM source. The known 0.19.0 non-square pixel regression (GitHub #77) is worked around by reprojecting py3dep output to exactly 1m square pixels in EPSG:5070 via rasterio. Option: pin py3dep once a fixed version is released.
