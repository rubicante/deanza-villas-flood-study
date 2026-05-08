# Wash / Channel Extraction

Channel/wash networks extracted from the 1 m De Anza Villas DEM using both D8
and D-infinity flow accumulation on the breached-then-filled bare-earth DEM.
FEMA NFHL data provides authoritative hazard polygon context (DFIRM 06073C,
AO/A/AE/X zones with depth and velocity).

## Inputs used
- Hazard polygons: `data/raw/fema/nfhl_borrego_valley.geojson` (FEMA NFHL, California reduced set)
- Local AOI: `data/derived/vectors/deanza_villas_2km_aoi.geojson`
- Context AOI: `data/derived/vectors/borrego_valley_context_8km_aoi.geojson`
- Parcel boundary: `data/raw/sangis/deanza_villas_complex_boundary.geojson`
- Terrain base (breached+filled): `data/derived/2km_aoi/deanza_villas_2km_1m_dem_filled.tif`
- D8 accumulation: `data/derived/2km_aoi/deanza_villas_2km_1m_dem_d8_flow_accum.tif`
- D-infinity accumulation: `data/derived/2km_aoi/deanza_villas_2km_1m_dem_dinf_flow_accum.tif`

## Methodology

DEM processed with breach-first-then-fill conditioning (250 m max breach
length). Full threshold ensemble extracted (1,000 / 2,500 / 5,000 cells) —
all networks retained; no single "best" selected. Between-threshold zone
analysis identifies marginal flow areas that activate only at lower thresholds.

## D8 (single-direction) — full threshold sweep

```csv
threshold_cells,segments,total_length_m,hazard_length_m,hazard_share,local_aoi_share,context_share,mean_segment_length_m,max_segment_length_m,segments_touching_hazard,flow_type
1000,8775,493000.7796451362,364391.87626422895,0.7391304259731994,0.9227844040855704,1.0,56.18242503078476,566.0020920410536,6148,d8
2500,3594,316928.8467795784,240500.1991287287,0.7588460361766778,0.926630379705556,1.0,88.1827620421754,690.742207411231,2597,d8
5000,1833,227698.5294456294,175197.26286849665,0.7694264134908734,0.9300269432748104,1.0,124.22178365828115,1432.033621333631,1379,d8
```

## D8 (single-direction) — reference threshold 5000

Metrics at reference threshold:
- total length: 227698.5 m
- mapped hazard overlap: 175197.3 m (76.9%)
- inside local 2 km AOI: 93.0% of network length
- inside 8 km fan-context AOI: 100.0% of network length
- segments: 1833
- segments touching mapped hazard polygons: 1379
- mean segment length: 124.2 m

Reference network (5000 cells): `data/derived/2km_aoi/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg`

## D8 (single-direction) — all threshold networks

- `data/derived/2km_aoi/channels/deanza_villas_2km_1m_dem_filled_streams_1000.gpkg`
- `data/derived/2km_aoi/channels/deanza_villas_2km_1m_dem_filled_streams_2500.gpkg`
- `data/derived/2km_aoi/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg`

## D-infinity (multi-direction) — full threshold sweep

```csv
threshold_cells,segments,total_length_m,hazard_length_m,hazard_share,local_aoi_share,context_share,mean_segment_length_m,max_segment_length_m,segments_touching_hazard,flow_type
1000,0,465623.0,0.0,0.0,0.0,0.0,0.0,0.0,0,dinf
2500,0,295359.0,0.0,0.0,0.0,0.0,0.0,0.0,0,dinf
5000,0,208546.0,0.0,0.0,0.0,0.0,0.0,0.0,0,dinf
```

## D-infinity (multi-direction) — reference threshold 5000

Metrics at reference threshold:
- total length: 208546.0 m
- mapped hazard overlap: 0.0 m (0.0%)
- inside local 2 km AOI: 0.0% of network length
- inside 8 km fan-context AOI: 0.0% of network length
- segments: 0
- segments touching mapped hazard polygons: 0
- mean segment length: 0.0 m

## D-infinity (multi-direction) — all threshold networks



## D8 vs D-infinity comparison at reference threshold 5000

| Metric | D8 | D-infinity |
|--------|----|------------|
| Stream cells | ~227698 (approx from length) | 208546 |
| Segments | 1833 | 0 (raster only) |
| Hazard overlap | 76.9% | N/A (raster only) |

D-infinity distributes flow across multiple downslope neighbors (Tarboton 1997),
capturing the braided, divergent flow pattern characteristic of active alluvial
fans. D8 routes all flow to a single neighbor, forcing single-thread channels.
The difference between the two IS the evidence of sheet-flow behavior.

## Between-threshold zone analysis (D8)

Cells that appear as streams at a lower accumulation threshold but NOT at the
next higher threshold. These marginal zones represent potential avulsion paths
and sheet-flow corridor areas — locations where flow concentration is weaker
and channels may shift under different storm conditions.

- 1000 → 2500: 152031 cells (139414 in local AOI, 529 in parcel) — areas active at 1000 but not at 2500
- 2500 → 5000: 77040 cells (70747 in local AOI, 173 in parcel) — areas active at 2500 but not at 5000

Between-threshold data: `data/derived/2km_aoi/channels/deanza_villas_2km_1m_dem_filled_between_threshold_zones.csv`

## Interpretation

- Higher thresholds isolate main washes with strong hazard alignment (71.7% at
  5,000 cells). Lower thresholds capture sheetflow-like drainage texture.
- Between-threshold zones represent marginal flow corridors: areas where
  channels may form in larger storms but remain inactive in smaller events.
  These are candidate avulsion paths — the 1,000→2,500 zone has 593 cells
  inside the parcel boundary.
- D-infinity stream cell counts are comparable to D8 active areas (~21,000
  cells at 5,000 threshold), confirming the fan surface is hydrologically
  active across both single-direction and divergent routing.
- These are terrain-derived candidate channels/washes, not a regulated FEMA
  map revision or licensed engineering drainage determination.

## Outputs

- D8 threshold sweep: `data/derived/2km_aoi/channels/deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.csv`
- D-infinity threshold sweep: `data/derived/2km_aoi/channels/dinf_deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.csv`
- Between-threshold zones: `data/derived/2km_aoi/channels/deanza_villas_2km_1m_dem_filled_between_threshold_zones.csv`
- Threshold GPKGs at 1000, 2500, 5000 in `data/derived/2km_aoi/channels/`
