# Borrego Springs flood study — quick handoff

Read these first:
- README.md
- outputs/reports/new_session_handoff.md
- outputs/reports/phase2_wash_extraction.md
- outputs/reports/phase3_parcel_overlay.md
- outputs/reports/phase3_fan_synthesis.md
- outputs/reports/phase4_satellite_validation.md

Key outputs:
- outputs/maps/phase2_channel_context.html
- outputs/maps/phase3_parcel_context.html
- outputs/maps/phase3_fan_synthesis.html
- outputs/maps/phase4_satellite_validation.html

Core data:
- data/vectors/deanza_villas_complex_boundary.geojson
- data/vectors/deanza_villas_parcel_polygons.geojson
- data/raw/fema/oes_know_your_hazards_flooding_borrego.geojson
- data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_filled.tif
- data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_slope_degrees.tif
- data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_d8_flow_accum.tif
- data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.csv
- data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg
- data/processed/terrain/deanza_villas_2km_1m/parcels/phase3_parcel_overlay_metrics.csv
- data/processed/terrain/deanza_villas_2km_1m/fan_synthesis/phase3_fan_synthesis_stats.csv
- data/processed/terrain/deanza_villas_2km_1m/validation_phase4/phase4_satellite_validation_candidates.csv
- data/processed/terrain/deanza_villas_2km_1m/validation_phase4/phase4_satellite_validation_selected.json

Scripts:
- scripts/phase2_extract_washes.py
- scripts/phase3_parcel_overlay.py
- scripts/phase3_fan_synthesis.py
- scripts/phase4_satellite_validation.py

Use:
- ./.venv/bin/python
- keep .env private

Summary:
- The terrain, parcel, and satellite validation steps are complete. De Anza Villas is on active concentrated-flow / alluvial-fan terrain, and the evidence is consistent.
