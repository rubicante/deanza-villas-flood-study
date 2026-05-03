# Phase 4 Satellite/Event Validation

Goal: check whether OPERA satellite surface-water products show positive evidence of wetting or flow concentration over the De Anza Villas AOI and parcel.

Run date: 2026-05-03 UTC

Search windows:
- OPERA DSWx-HLS: 2023-08-15 to 2023-09-15 (max 20 items)
- OPERA DSWx-S1: 2024-08-20 to 2024-09-05 (max 20 items)

Local AOI: data/vectors/deanza_villas_2km_aoi.geojson
Parcel boundary: data/vectors/deanza_villas_complex_boundary.geojson
FEMA layer: data/raw/fema/oes_know_your_hazards_flooding_borrego.geojson
Channel network: data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg

Candidate summary:
- OPERA DSWx-HLS: 15 candidates, 8 with local-AOI water, 1 with parcel water, best scene 2023-08-22 (OPERA_L3_DSWx-HLS_T11SNS_20230822T182232Z_20230824T134308Z_L8_30_v1.0)
  best counts: local=12, parcel=1, total water=73516, local share=0.924%, parcel share=1.099%
  aggregate local water pixels across candidates: 39; parcel water pixels: 1
- OPERA DSWx-S1: 5 candidates, 0 with local-AOI water, 0 with parcel water, best scene 2024-08-25 (OPERA_L3_DSWx-S1_T11SNS_20240825T134510Z_20251107T082429Z_S1A_30_v1.0)
  best counts: local=0, parcel=0, total water=327509, local share=0.000%, parcel share=0.000%
  aggregate local water pixels across candidates: 0; parcel water pixels: 0

Selected scenes:
- OPERA DSWx-HLS / 2023-08-22 / OPERA_L3_DSWx-HLS_T11SNS_20230822T182232Z_20230824T134308Z_L8_30_v1.0: local water 12, parcel water 1, overall water 73516
  browse: https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-public/OPERA_L3_DSWX-HLS_PROVISIONAL_V1/OPERA_L3_DSWx-HLS_T11SNS_20230822T182232Z_20230824T134308Z_L8_30_v1.0_BROWSE.png
  data: https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-protected/OPERA_L3_DSWX-HLS_PROVISIONAL_V1/OPERA_L3_DSWx-HLS_T11SNS_20230822T182232Z_20230824T134308Z_L8_30_v1.0_B01_WTR.tif
  local file: /home/hermes/workspace/borrego-flood-study/data/processed/terrain/deanza_villas_2km_1m/validation_phase4/downloads/OPERA_L3_DSWx-HLS_T11SNS_20230822T182232Z_20230824T134308Z_L8_30_v1.0_B01_WTR.tif
  browse file: /home/hermes/workspace/borrego-flood-study/data/processed/terrain/deanza_villas_2km_1m/validation_phase4/downloads/OPERA_L3_DSWx-HLS_T11SNS_20230822T182232Z_20230824T134308Z_L8_30_v1.0_BROWSE.png
- OPERA DSWx-S1 / 2024-08-25 / OPERA_L3_DSWx-S1_T11SNS_20240825T134510Z_20251107T082429Z_S1A_30_v1.0: local water 0, parcel water 0, overall water 327509
  browse: https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-public/OPERA_L3_DSWX-S1_V1/OPERA_L3_DSWx-S1_T11SNS_20240825T134510Z_20251107T082429Z_S1A_30_v1.0_BROWSE.png
  data: https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-protected/OPERA_L3_DSWX-S1_V1/OPERA_L3_DSWx-S1_T11SNS_20240825T134510Z_20251107T082429Z_S1A_30_v1.0_B01_WTR.tif
  local file: /home/hermes/workspace/borrego-flood-study/data/processed/terrain/deanza_villas_2km_1m/validation_phase4/downloads/OPERA_L3_DSWx-S1_T11SNS_20240825T134510Z_20251107T082429Z_S1A_30_v1.0_B01_WTR.tif
  browse file: /home/hermes/workspace/borrego-flood-study/data/processed/terrain/deanza_villas_2km_1m/validation_phase4/downloads/OPERA_L3_DSWx-S1_T11SNS_20240825T134510Z_20251107T082429Z_S1A_30_v1.0_BROWSE.png

Interpretation:
- DSWx-HLS provides positive local evidence: the best scene (2023-08-22) detected 12 water/inundation pixels inside the 2 km AOI and 1 pixel inside the parcel boundary.
- DSWx-S1 covered the study area, but the searched scenes did not flag local-AOI water pixels. The S1 footprint still showed broader-valley water detections, so the absence at the parcel is weak evidence only.
- Overall: the satellite record provides positive evidence of wetting in the valley and at least one HLS local detection near the study area; lack of S1 parcel pixels is not evidence of no flooding because the product sampling is sparse and scene timing is limited.

Outputs:
- Report: outputs/reports/phase4_satellite_validation.md
- Map: outputs/maps/phase4_satellite_validation.html
- Candidate CSV: data/processed/terrain/deanza_villas_2km_1m/validation_phase4/phase4_satellite_validation_candidates.csv
- Candidate JSON: data/processed/terrain/deanza_villas_2km_1m/validation_phase4/phase4_satellite_validation_candidates.json
- Selected JSON: data/processed/terrain/deanza_villas_2km_1m/validation_phase4/phase4_satellite_validation_selected.json
- Download cache: data/processed/terrain/deanza_villas_2km_1m/validation_phase4/downloads/

Note: Sentinel-1 GRD fallback was not needed because OPERA DSWx coverage was sufficient for a positive wetting check in this pass.
