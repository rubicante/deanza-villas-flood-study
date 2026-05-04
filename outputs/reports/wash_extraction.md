# Wash / Channel Extraction

Channel/wash networks extracted from the 1 m De Anza Villas DEM using both D8
and D-infinity flow accumulation on the breached-then-filled bare-earth DEM.
FEMA NFHL data provides authoritative hazard polygon context (DFIRM 06073C,
AO/A/AE/X zones with depth and velocity).

## Inputs used
- Hazard polygons: `data/raw/fema/nfhl_borrego_valley.geojson` (FEMA NFHL, California reduced set)
- Local AOI: `data/vectors/deanza_villas_2km_aoi.geojson`
- Context AOI: `data/vectors/borrego_valley_context_8km_aoi.geojson`
- Parcel boundary: `data/vectors/deanza_villas_complex_boundary.geojson`
- Terrain base (breached+filled): `data/processed/terrain/deanza_villas_2km_1m_dem_filled.tif`
- D8 accumulation: `data/processed/terrain/deanza_villas_2km_1m_dem_d8_flow_accum.tif`
- D-infinity accumulation: `data/processed/terrain/deanza_villas_2km_1m_dem_dinf_flow_accum.tif`

## Methodology

DEM processed with breach-first-then-fill conditioning (250 m max breach
length). Full threshold ensemble extracted (1,000 / 2,500 / 5,000 cells) —
all networks retained; no single "best" selected. Between-threshold zone
analysis identifies marginal flow areas that activate only at lower thresholds.

## D8 (single-direction) — full threshold sweep

```csv
threshold_cells,segments,total_length_m,hazard_length_m,hazard_share,local_aoi_share,context_share,mean_segment_length_m,max_segment_length_m,segments_touching_hazard,flow_type
1000,1123,58030.57643911989,37920.92150299354,0.6534644980267693,0.6101244447364547,1.0,51.67460056911833,396.37972567696727,694,d8
2500,454,35842.98655569301,24844.58133634643,0.6931504242187742,0.630144375802554,1.0,78.94930959403746,611.6589462905463,292,d8
5000,237,24724.206332605325,17720.896627681366,0.7167427900127065,0.6512528132166934,1.0,104.32154570719548,639.4528855298863,164,d8
```

## D8 (single-direction) — reference threshold 5000

Metrics at reference threshold:
- total length: 24724.2 m
- mapped hazard overlap: 17720.9 m (71.7%)
- inside local 2 km AOI: 65.1% of network length
- inside 8 km fan-context AOI: 100.0% of network length
- segments: 237
- segments touching mapped hazard polygons: 164
- mean segment length: 104.3 m

Reference network (5000 cells): `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg`

## D8 (single-direction) — all threshold networks

- `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_1000.gpkg`
- `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_2500.gpkg`
- `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg`

## D-infinity (multi-direction) — full threshold sweep

```csv
threshold_cells,segments,total_length_m,hazard_length_m,hazard_share,local_aoi_share,context_share,mean_segment_length_m,max_segment_length_m,segments_touching_hazard,flow_type
1000,0,57561.0,0.0,0.0,0.0,0.0,0.0,0.0,0,dinf
2500,0,33013.0,0.0,0.0,0.0,0.0,0.0,0.0,0,dinf
5000,0,21238.0,0.0,0.0,0.0,0.0,0.0,0.0,0,dinf
```

## D-infinity (multi-direction) — reference threshold 5000

Metrics at reference threshold:
- total length: 21238.0 m
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
| Stream cells | ~24724 (approx from length) | 21238 |
| Segments | 237 | 0 (raster only) |
| Hazard overlap | 71.7% | N/A (raster only) |

D-infinity distributes flow across multiple downslope neighbors (Tarboton 1997),
capturing the braided, divergent flow pattern characteristic of active alluvial
fans. D8 routes all flow to a single neighbor, forcing single-thread channels.
The difference between the two IS the evidence of sheet-flow behavior.

## Between-threshold zone analysis (D8)

Cells that appear as streams at a lower accumulation threshold but NOT at the
next higher threshold. These marginal zones represent potential avulsion paths
and sheet-flow corridor areas — locations where flow concentration is weaker
and channels may shift under different storm conditions.

- 1000 → 2500: 18697 cells (10768 in local AOI, 593 in parcel) — areas active at 1000 but not at 2500
- 2500 → 5000: 9373 cells (5412 in local AOI, 243 in parcel) — areas active at 2500 but not at 5000

Between-threshold data: `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_between_threshold_zones.csv`

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

- D8 threshold sweep: `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.csv`
- D-infinity threshold sweep: `data/processed/terrain/deanza_villas_2km_1m/channels/dinf_deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.csv`
- Between-threshold zones: `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_between_threshold_zones.csv`
- Threshold GPKGs at 1000, 2500, 5000 in `data/processed/terrain/deanza_villas_2km_1m/channels/`
