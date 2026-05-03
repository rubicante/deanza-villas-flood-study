# Handoff Summary

Date: 2026-05-02

## What was done

I established a working terrain-analysis chain for the Borrego Springs / DeAnza Villas study.

### Broader context prototype
- AOI: `data/vectors/borrego_valley_context_8km_aoi.geojson`
- Prototype DEM: `data/raw/dem/borrego_valley_3dep_10m.tif`
- Prototype terrain outputs:
  - `data/processed/terrain/borrego_valley_3dep_10m_filled.tif`
  - `data/processed/terrain/borrego_valley_3dep_10m_slope_degrees.tif`
  - `data/processed/terrain/borrego_valley_3dep_10m_d8_flow_accum.tif`

### Local analysis-grade refinement
- AOI: `data/vectors/deanza_villas_2km_aoi.geojson`
- 1 m DEM: `data/raw/dem/deanza_villas_2km_1m_dem.tif`
- Derived terrain outputs:
  - `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_filled.tif`
  - `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_slope_degrees.tif`
  - `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_d8_flow_accum.tif`

## Key findings
- Borrego Springs is an alluvial-fan environment; the important question is flow-path concentration across fan surfaces, not just wash proximity.
- The earlier 10 m DEM was only for workflow validation.
- The 1 m DEM is the more useful analysis-grade local terrain dataset.
- WhiteboxTools works reliably once file paths are resolved to absolute paths.
- TNMAccess was slow/timeouting for this use case, so `py3dep` was the practical route for the 1 m local DEM fetch.

## Terrain stats for the local 1 m DEM
- Shape: 1735 x 1722
- CRS: EPSG:5070
- Cell size: about 0.83 m x 0.85 m
- Elevation range: 188.26 m to 494.14 m

## Files to know first
- `README.md`
- `scripts/init_env.py`
- `scripts/phase2_fetch_dem.py`
- `scripts/phase2_terrain_metrics.py`
- `outputs/reports/phase2_start_note.md`
- `outputs/reports/phase2_refinement_note.md`

## Next steps
1. Extract channels / washes from the 1 m terrain.
2. Compare concentrated flow paths against mapped hazards and fan context.
3. Refine accumulation thresholds and inspect candidate channels visually.
4. Only after that, move to parcel-precise analysis if parcel geometry is available.

## Environment notes
- Project-local `.env` holds credentials/config.
- `.env`, `.venv`, caches, and outputs are gitignored.
- Use `./.venv/bin/python` in this environment.
