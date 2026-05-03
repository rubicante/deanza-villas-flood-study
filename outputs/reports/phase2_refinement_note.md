# Refinement Note

Analysis-grade local terrain data has now been fetched and conditioned for the DeAnza Villas context area.

Local analysis AOI:
- `data/vectors/deanza_villas_2km_aoi.geojson`
- 2 km radius around the DeAnza Villas reference point

Analysis-grade DEM:
- `data/raw/dem/deanza_villas_2km_1m_dem.tif`
- Source: USGS 3DEP 1 m DEM via `py3dep`
- CRS: EPSG:5070
- Shape: 1735 x 1722
- Cell size: about 0.83 m x 0.85 m
- Elevation range: 188.26 m to 494.14 m

Derived terrain outputs:
- `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_filled.tif`
- `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_slope_degrees.tif`
- `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_d8_flow_accum.tif`

Notes:
- The 1 m DEM is the analysis-grade refinement step beyond the earlier 10 m prototype.
- The broader 8 km Borrego context DEM remains available for wider framing.
- Next useful step is stream/channel extraction and comparing concentrated flow paths against the fan context and mapped hazards.
