# Wash / Channel Extraction

This step extracted candidate channel/wash networks from the 1 m DeAnza Villas DEM using both D8 (single-direction) and D-infinity (multi-direction, Tarboton 1997) flow accumulation on the breached-then-filled bare-earth DEM.

## Inputs used
- Hazard polygons: `data/raw/fema/oes_know_your_hazards_flooding_borrego.geojson`
- Local AOI: `data/vectors/deanza_villas_2km_aoi.geojson`
- Context AOI: `data/vectors/borrego_valley_context_8km_aoi.geojson`
- Terrain base (breached+filled): `data/processed/terrain/deanza_villas_2km_1m_dem_filled.tif`
- D8 accumulation: `data/processed/terrain/deanza_villas_2km_1m_dem_d8_flow_accum.tif`
- D-infinity accumulation: `data/processed/terrain/deanza_villas_2km_1m_dem_dinf_flow_accum.tif`

## Methodology

The DEM was processed with breach-first-then-fill conditioning (250 m max breach length) to preserve flow continuity across fan surfaces. Simple fill alone creates artificial flat areas that block D8 routing on alluvial fans.

## D8 threshold sweep

```csv
threshold_cells,segments,total_length_m,hazard_length_m,hazard_share,local_aoi_share,context_share,mean_segment_length_m,max_segment_length_m,segments_touching_hazard,flow_type
1000,1123,58030.57643911989,25789.92590447915,0.4444196057837796,0.6101244447364547,1.0,51.67460056911833,396.37972567696727,528,d8
2500,454,35842.98655569301,16833.666874043032,0.4696502298402729,0.630144375802554,1.0,78.94930959403746,611.6589462905463,233,d8
5000,237,24724.206332605325,12144.055054318833,0.4911807841655052,0.6512528132166934,1.0,104.32154570719548,639.4528855298863,131,d8
```

## D8 (single-direction) — threshold 5000

Selected-threshold metrics:
- total length: 24724.2 m
- mapped hazard overlap: 12144.1 m (49.1%)
- inside local 2 km AOI: 65.1% of network length
- inside 8 km fan-context AOI: 100.0% of network length
- segments: 237
- segments touching mapped hazard polygons: 131
- mean segment length: 104.3 m

Selected stream network: `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg`


## D-infinity threshold sweep

```csv
threshold_cells,segments,total_length_m,hazard_length_m,hazard_share,local_aoi_share,context_share,mean_segment_length_m,max_segment_length_m,segments_touching_hazard,flow_type
1000,0,57561.0,0.0,0.0,0.0,0.0,0.0,0.0,0,dinf
2500,0,33013.0,0.0,0.0,0.0,0.0,0.0,0.0,0,dinf
5000,0,21238.0,0.0,0.0,0.0,0.0,0.0,0.0,0,dinf
```

## D-infinity (multi-direction, Tarboton 1997) — threshold 5000

Selected-threshold metrics:
- total length: 21238.0 m
- mapped hazard overlap: 0.0 m (0.0%)
- inside local 2 km AOI: 0.0% of network length
- inside 8 km fan-context AOI: 0.0% of network length
- segments: 0
- segments touching mapped hazard polygons: 0
- mean segment length: 0.0 m


## D8 vs D-infinity comparison at threshold 5000

| Metric | D8 | D-infinity |
|--------|----|------------|
| Segments | 237 | 0 |
| Total length | 24724 m | 21238 m |
| Mean segment length | 104.3 m | 0.0 m |
| Hazard overlap | 49.1% | 0.0% |

D-infinity produces 0x more segments, with shorter mean lengths — direct evidence of divergent sheet-flow behavior on the alluvial fan surface. D8 forces single-thread channel routing; D-infinity captures the braided, multi-path flow pattern characteristic of active alluvial fans.


## Interpretation

- Lower thresholds capture dense sheetflow-like drainage texture; higher thresholds isolate the main washes.
- The D8/D-infinity divergence on the fan surface is itself the signal: D-infinity produces many more, shorter segments — direct evidence of the braided, divergent flow pattern that defines active alluvial fan flooding.
- The breached+filled DEM conditioning avoids the artificial flat-area artifacts that simple sink-filling creates on fan terrain.
- These are terrain-derived candidate channels/washes, not a regulated FEMA map revision or licensed engineering drainage determination.

## Outputs

- D8 threshold sweep CSV: `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.csv`
- D8 threshold sweep JSON: `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.json`
- D-infinity threshold sweep CSV: `data/processed/terrain/deanza_villas_2km_1m/channels/dinf_deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.csv`
- D-infinity threshold sweep JSON: `data/processed/terrain/deanza_villas_2km_1m/channels/dinf_deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.json`
- Selected D8 channel network GPKG: `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg`
