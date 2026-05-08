# Satellite / Event Validation

Goal: check whether OPERA satellite surface-water products show positive evidence of wetting or flow concentration over the De Anza Villas AOI and parcel.

Run date: 2026-05-08 UTC

Search windows:
- OPERA DSWx-HLS 2023-2024 all seasons: 2023-01-01 to 2024-12-31 (max 400 items)
- OPERA DSWx-S1 2024 viable coverage: 2024-08-25 to 2024-12-31 (max 100 items)

Local AOI: data/derived/vectors/deanza_villas_2km_aoi.geojson
Parcel boundary: data/raw/sangis/deanza_villas_complex_boundary.geojson
FEMA layer: data/raw/fema/nfhl_borrego_valley.geojson
Channel network: data/derived/2km_aoi/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg

Candidate summary:
- OPERA DSWx-HLS 2023-2024 all seasons: 344 candidates, 169 with local-AOI water, 1 with parcel water, best scene 2024-02-07 (OPERA_L3_DSWx-HLS_T11SNS_20240207T181628Z_20240209T161841Z_L8_30_v1.0)
  best counts: local=182, parcel=0, total water=304221, local share=1.132%, parcel share=0.000%
  aggregate local water pixels across candidates: 1168; parcel water pixels: 1
- OPERA DSWx-S1 2024 viable coverage: 37 candidates, 0 with local-AOI water, 0 with parcel water, best scene 2024-12-11 (OPERA_L3_DSWx-S1_T11SNS_20241211T134458Z_20241213T113344Z_S1A_30_v1.0)
  best counts: local=0, parcel=0, total water=329159, local share=0.000%, parcel share=0.000%
  aggregate local water pixels across candidates: 0; parcel water pixels: 0

Selected scenes:
- OPERA DSWx-HLS 2023-2024 all seasons / 2024-02-07 / OPERA_L3_DSWx-HLS_T11SNS_20240207T181628Z_20240209T161841Z_L8_30_v1.0: local water 182, parcel water 0, overall water 304221
  browse: https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-public/OPERA_L3_DSWX-HLS_PROVISIONAL_V1/OPERA_L3_DSWx-HLS_T11SNS_20240207T181628Z_20240209T161841Z_L8_30_v1.0_BROWSE.png
  data: https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-protected/OPERA_L3_DSWX-HLS_PROVISIONAL_V1/OPERA_L3_DSWx-HLS_T11SNS_20240207T181628Z_20240209T161841Z_L8_30_v1.0_B01_WTR.tif
  local file: /home/hermes/workspace/deanza-villas-flood-study/data/derived/2km_aoi/satellite_validation/downloads/OPERA_L3_DSWx-HLS_T11SNS_20240207T181628Z_20240209T161841Z_L8_30_v1.0_B01_WTR.tif
  browse file: /home/hermes/workspace/deanza-villas-flood-study/data/derived/2km_aoi/satellite_validation/downloads/OPERA_L3_DSWx-HLS_T11SNS_20240207T181628Z_20240209T161841Z_L8_30_v1.0_BROWSE.png
- OPERA DSWx-S1 2024 viable coverage / 2024-12-11 / OPERA_L3_DSWx-S1_T11SNS_20241211T134458Z_20241213T113344Z_S1A_30_v1.0: local water 0, parcel water 0, overall water 329159
  browse: https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-public/OPERA_L3_DSWX-S1_V1/OPERA_L3_DSWx-S1_T11SNS_20241211T134458Z_20241213T113344Z_S1A_30_v1.0_BROWSE.png
  data: https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-protected/OPERA_L3_DSWX-S1_V1/OPERA_L3_DSWx-S1_T11SNS_20241211T134458Z_20241213T113344Z_S1A_30_v1.0_B01_WTR.tif
  local file: /home/hermes/workspace/deanza-villas-flood-study/data/derived/2km_aoi/satellite_validation/downloads/OPERA_L3_DSWx-S1_T11SNS_20241211T134458Z_20241213T113344Z_S1A_30_v1.0_B01_WTR.tif
  browse file: /home/hermes/workspace/deanza-villas-flood-study/data/derived/2km_aoi/satellite_validation/downloads/OPERA_L3_DSWx-S1_T11SNS_20241211T134458Z_20241213T113344Z_S1A_30_v1.0_BROWSE.png

Interpretation:
- DSWx-HLS did not produce positive local water pixels in the searched window.
- Overall: the satellite record provides positive evidence of wetting in the valley and at least one HLS local detection near the study area; lack of S1 parcel pixels is not evidence of no flooding because the product sampling is sparse and scene timing is limited.

Outputs:
- Report: outputs/reports/satellite_validation.md
- Map: outputs/maps/satellite_validation.html
- Candidate CSV: data/derived/2km_aoi/satellite_validation/satellite_validation_candidates.csv
- Candidate JSON: data/derived/2km_aoi/satellite_validation/satellite_validation_candidates.json
- Selected JSON: data/derived/2km_aoi/satellite_validation/satellite_validation_selected.json
- Download cache: `data/derived/2km_aoi/satellite_validation/downloads`

Note: Sentinel-1 GRD fallback was not needed because OPERA DSWx coverage was sufficient for a positive wetting check in this pass.
