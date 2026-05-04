# Wash / Channel Extraction

This step extracted candidate channel/wash networks from the 1 m DeAnza Villas D8 flow-accumulation surface and compared them against the mapped county/FEMA-derived flood-hazard polygons and the local fan context AOIs.

## Inputs used
- Hazard polygons: `data/raw/fema/oes_know_your_hazards_flooding_borrego.geojson`
- Local AOI: `data/vectors/deanza_villas_2km_aoi.geojson`
- Context AOI: `data/vectors/borrego_valley_context_8km_aoi.geojson`
- Terrain base: `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_filled.tif`
- D8 accumulation: `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_d8_flow_accum.tif`

## Threshold sweep results

```csv
threshold_cells,segments,total_length_m,hazard_length_m,hazard_share,local_aoi_share,context_share,mean_segment_length_m,max_segment_length_m,segments_touching_hazard
1000,1712,76026.91593661907,32992.22447708699,0.4339545287433654,0.57557072387395,1.0,44.40824529008123,386.5694132972256,757
2500,694,45873.184795116365,20783.519598230665,0.4530646758243667,0.5971633066001563,1.0,66.09968990650773,412.6285706059047,352
5000,359,31848.43251234164,15057.132478960775,0.472774679668331,0.6187737946459444,1.0,88.71429669175944,634.6714536909791,194
```

## Working threshold choice

Selected threshold: 5000 accumulation cells. It sits in the top hazard-overlap band and is the most concise network among thresholds within 95% of the maximum hazard-share score.

Selected-threshold metrics:
- total length: 31848.4 m
- mapped hazard overlap: 15057.1 m (47.3%)
- inside local 2 km AOI: 61.9% of network length
- inside 8 km fan-context AOI: 100.0% of network length
- segments touching mapped hazard polygons: 194 of 359

Selected stream network: `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg`

## Interpretation

- Lower thresholds capture dense sheetflow-like drainage texture but create a very large network that is harder to interpret.
- Higher thresholds isolate the main washes and produce a cleaner comparison layer for hazard context review.
- The mapped flood polygons intersect the extracted network substantially enough to support a real channel/wash context comparison rather than a purely synthetic drainage result.
- For the next pass, the selected network is the right base layer for visual inspection against hazard polygons, fan context, and any parcel geometry once available.

## Context caveat

These are terrain-derived candidate channels/washes, not a regulated FEMA map revision or a licensed engineering drainage determination.

## Outputs

- Threshold sweep CSV: `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.csv`
- Threshold sweep JSON: `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.json`
- Selected channel network GPKG: `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg`
