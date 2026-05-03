# Parcel Overlay

This step wired the authoritative De Anza Villas parcel geometry into the selected 5000-cell channel network and re-ran the overlay metrics against the hazard and fan-context layers.

## Inputs used
- Selected stream network: `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg`
- Parcel boundary: `data/vectors/deanza_villas_complex_boundary.geojson`
- Parcel polygons: `data/vectors/deanza_villas_parcel_polygons.geojson` (67 features)
- Hazard polygons: `data/raw/fema/oes_know_your_hazards_flooding_borrego.geojson` (1632 features)
- Local AOI: `data/vectors/deanza_villas_2km_aoi.geojson`
- Context AOI: `data/vectors/borrego_valley_context_8km_aoi.geojson`

## Parcel-aware overlay metrics

```csv
layer_name,total_length_m,inside_parcel_m,inside_hazard_m,inside_parcel_and_hazard_m,outside_parcel_m,parcel_share,hazard_share,hazard_share_within_parcel,segments,segments_touching_parcel,segments_touching_hazard,segments_touching_both
selected_stream_network,31848.432512341642,904.63176742153,15057.132478960777,875.1716895473422,30943.80074492011,0.028404279145322914,0.472774679668331,0.9674341771590028,359,22,194,22
```

Key readout:
- network length inside parcel boundary: 904.6 m (2.8%)
- network length inside mapped hazard polygons: 15057.1 m (47.3%)
- network length inside both parcel boundary and hazard polygons: 875.2 m
- hazard share within parcel boundary: 96.7%
- segments touching parcel boundary: 22 of 359
- segments touching hazard polygons: 194 of 359
- segments touching both parcel and hazard: 22 of 359

Clipped parcel-only stream layer: `data/processed/terrain/deanza_villas_2km_1m/parcels/deanza_villas_2km_1m_dem_filled_streams_5000_in_parcel.gpkg`

## Interpretation

- The authoritative boundary confirms how much of the selected drainage network actually crosses or sits within the De Anza Villas parcel complex.
- Comparing the network to the dissolved parcel boundary avoids using a hand-drawn approximation for parcel-scale risk context.
- The hazard overlap remains substantial after parcel-aware clipping, so the parcel context does not eliminate the channel/wash signal; it localizes it.
- The parcel polygons are preserved as a separate layer for later per-APN interrogation, while the dissolved boundary is the canonical single-file parcel geometry.

## Context caveat

These are terrain-derived and parcel-overlay context metrics, not a licensed engineering flood determination or FEMA map revision.

## Outputs

- Metrics CSV: `data/processed/terrain/deanza_villas_2km_1m/parcels/phase3_parcel_overlay_metrics.csv`
- Metrics JSON: `data/processed/terrain/deanza_villas_2km_1m/parcels/phase3_parcel_overlay_metrics.json`
- Parcel-only stream GPKG: `data/processed/terrain/deanza_villas_2km_1m/parcels/deanza_villas_2km_1m_dem_filled_streams_5000_in_parcel.gpkg`
- Canonical parcel boundary: `data/vectors/deanza_villas_complex_boundary.geojson`
- Parcel polygon set: `data/vectors/deanza_villas_parcel_polygons.geojson`
- Canonical parcel overlay map: `outputs/maps/phase3_parcel_context.html`
