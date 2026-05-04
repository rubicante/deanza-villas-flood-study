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

### Tier 2 — Hazard evidence quality improvements

- [ ] Fetch authoritative FEMA NFHL data for Borrego Valley from ArcGIS REST (California reduced set). Endpoint: `https://services2.arcgis.com/Uq9r85Potqm3MfRV/arcgis/rest/services/S_FLD_HAZ_AR_Reduced_Set_CA_wm/FeatureServer/0`. Query by spatial extent around De Anza Villas (33.256, -116.375, 8km radius), export as GeoJSON. Confirmed: 110 AO zone features for DFIRM 06073C with depth (1–6 ft), velocity (3–11 ft/sec), plus AE zones with STATIC_BFE. Fields: FLD_ZONE, ZONE_SUBTY, DEPTH, VELOCITY, STATIC_BFE, SFHA_TF, DFIRM_ID, STUDY_TYP, SOURCE_CIT, LEN_UNIT, VEL_UNIT, plus revert fields. Caveat: this CA reduced set (Nov 2023) pre-filters out Zone D (undetermined) and Zone X "Area of Minimal Flood Hazard" — acceptable for positive hazard evidence; Zone D areas are independently assessed by terrain/satellite analysis. Save as `data/raw/fema/nfhl_borrego_valley.geojson`. Update study.yaml `hazard_polygons` path and study_manifest.yaml reference. Replace current `data/raw/fema/oes_know_your_hazards_flooding_borrego.geojson` (1,632 features, FP100/FW100 only, no depth/velocity).
- [ ] [MANUAL DOWNLOAD REQUIRED] Download full California NFHL state file geodatabase from FEMA MSC (https://msc.fema.gov/portal/advanceSearch → California → "NFHL Data-State"). This contains the complete unfiltered NFHL including Zone D, Zone X minimal hazard, and all ancillary layers not in the reduced set. FEMA updates state extracts every two weeks. The MSC portal has TLS cipher-suite restrictions that block automated download from this server — must be done in a browser. Extract the Borrego panels (DFIRM 06073C) and save as `data/raw/fema/nfhl_ca_full_borrego.gpkg` (or similar). This is additive to the reduced-set fetch above; not blocking.
- [ ] Refactor extract_washes.py to keep the full threshold ensemble instead of selecting one "best." Export all threshold networks (1000, 2500, 5000, plus any new thresholds from D-infinity) and add a zone-between-thresholds analysis: areas activated only at lower accumulation thresholds are potential avulsion paths.
- [ ] Expand satellite_validation.py temporal search. Researched: DSWx-HLS has robust year-round coverage at this AOI (38-46 scenes per season, 2023-2024, all seasons). DSWx-S1 has zero scenes in 2023 and only viable from late summer 2024 (12 summer, 25 fall). Verified via earthaccess.search_data across 16 product/year/season windows. Recommended: expand HLS to full-year 2023-2024 (`temporal: ("2023-01-01", "2024-12-31"), max_items: 400`) and expand S1 to match actual catalog availability (`temporal: ("2024-08-25", "2024-12-31"), max_items: 100`). Optionally retain 8 seasonal HLS entries for per-season reporting. Verification script and CSV at kanban workspace `t_bb736bc5`.

### Tier 3 — Additional diagnostic terrain metrics

- [ ] Compute profile curvature (wbt.profile_curvature or equivalent) — distinguishes convex/channelized from concave/sheet-flow fan surfaces. Most diagnostic single metric for identifying active fan lobes and avulsion-prone zones.
- [ ] Compute Topographic Position Index (TPI) — reveals local high/low positions, subtle channel-levee systems, abandoned lobes, topographic traps. At 1m resolution this shows features invisible to slope alone.
- [ ] Compute HAND (Height Above Nearest Drainage) as relative position index only — use as evidence of where channel avulsion would impact the parcel, not as an inundation depth proxy. Follow FEMA alluvial fan guidance: HAND is relative terrain evidence, not primary depth indicator on active fans.
- [ ] Compare parcel-scale roughness magnitude against active/inactive fan surface benchmarks from DRI 2015 mapping. Researched: no public downloadable GIS layer exists (checked SanGIS, SANDAG, ArcGIS Online, FEMA Risk MAP). The DRI 2015 presentation PDF (https://cdn.ymaws.com/floodplain.org/resource/resmgr/2015Conference/Wednesday/Borrego-Springs-Alluvial-Fan.pdf) contains clear maps suitable for digitization. Page 20 is the best source: binary active/inactive fan areas with lat/lon graticule ticks, scale bar, and road/drainage context. Page 14 has richer geomorphic unit classes (Qa1-Qa4, Qf1a-Qf5, etc.) if age-specific comparison is needed. Digitization plan: render pages at 300-600 dpi → crop to map frame → georeference in QGIS using graticule ticks as GCPs → affine transform → digitize polygon classes → reproject to EPSG:5070. Expected confidence: moderate for broad extents and large polygons, low-moderate for small inactive polygons. Also consider contacting SanGIS/County Flood Control to request original GIS — the DRI work was contractor-produced and likely exists as CAD/GIS production data even if not publicly served. Detailed plan at kanban workspace `t_f11b4a8f`. Roughness comparison method: Frankel & Dolan 2007 — active fan lobes are rough, inactive surfaces smooth out with age (JGR Earth Surface, doi:10.1029/2006JF000644).

### Tier 4 — Dependency hygiene

- [ ] py3dep 0.19.0 retained (not removed). The Eastern SD 2017 QL2 lidar tiles don't cover the parcel; py3dep WCS mosaic is the correct DEM source. The known 0.19.0 non-square pixel regression (GitHub #77) is worked around by reprojecting py3dep output to exactly 1m square pixels in EPSG:5070 via rasterio. Option: pin py3dep once a fixed version is released.
