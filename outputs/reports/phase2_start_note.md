# Phase 2 Start Note

Prototype terrain processing has started for the Borrego Valley context area.

Working AOI:
- `data/vectors/borrego_valley_context_8km_aoi.geojson`
- 8 km radius around the DeAnza Villas reference point

Prototype DEM:
- `data/raw/dem/borrego_valley_3dep_10m.tif`
- Source: 3DEP via py3dep
- Resolution: 10 m
- CRS: EPSG:5070

Initial terrain derivatives:
- `data/processed/terrain/borrego_valley_3dep_10m_filled.tif`
- `data/processed/terrain/borrego_valley_3dep_10m_slope_degrees.tif`
- `data/processed/terrain/borrego_valley_3dep_10m_d8_flow_accum.tif`

Scripts added:
- `scripts/phase2_fetch_dem.py`
- `scripts/phase2_terrain_metrics.py`

Notes:
- This is a prototype terrain chain to validate the workflow.
- It is not yet the analysis-grade lidar source-of-record.
- Next refinement should be swapping in the Borrego-area QL2 lidar / hydro-flattened source DEM and then iterating on channel extraction thresholds.
