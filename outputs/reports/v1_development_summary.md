# V1 Development Summary — historical background

This is the short consolidated record of the version-1 development log. It preserves the choices that mattered for the final Borrego Springs / De Anza Villas analysis and drops the step-by-step workflow noise.

## What changed during v1

1. Broader context prototype
- Established the study framing with the 8 km Borrego Valley context AOI.
- Used a 10 m 3DEP DEM first, mainly to validate the terrain-processing chain.
- Confirmed the project needed a better local source for parcel-scale interpretation.

2. Local analysis-grade refinement
- Switched to the 2 km De Anza Villas AOI and a 1 m 3DEP DEM via `py3dep`.
- Treated the 1 m DEM as the analysis-grade local terrain source of record.
- Kept the 8 km context AOI as the wider fan-framing layer.
- Noted that WhiteboxTools worked reliably once absolute paths were used.
- Noted that TNMAccess was too slow / fragile for this use case.

3. Channel / wash extraction
- Ran threshold sweeps on the 1 m D8 accumulation surface.
- Chose 5000 accumulation cells as the working threshold because it was the most concise network while still staying in the high hazard-overlap band.
- Preserved the selected network as the basis for later visual and parcel-aware review.

4. Parcel-aware overlay
- Replaced any hand-drawn parcel approximation with the canonical dissolved De Anza Villas boundary.
- Kept the parcel polygons as a separate layer for later APN-level work.
- Confirmed the selected wash network still crossed the parcel complex and still overlapped mapped hazard polygons substantially.

5. Fan-activity synthesis
- Used the County/Boyle guidance and DRI fan mapping together with the 1 m terrain derivatives.
- Treated the site as an active alluvial-fan setting with concentrated-flow exposure and channel mobility, not as a fixed-channel problem.
- Kept the interpretation bounded to terrain and documentary evidence, not a formal engineering flood determination.

6. Satellite validation
- Checked OPERA DSWx-HLS and DSWx-S1 products against the AOI and parcel.
- Kept the 2023-08-22 HLS scene as the best positive wetting evidence.
- Treated the lack of local S1 water pixels as weak negative evidence only, not proof of no flooding.
- Did not need the Sentinel-1 GRD fallback.

## Canonical outputs retained

- Context map: `outputs/maps/phase1_context.html`
- Parcel overlay map: `outputs/maps/phase3_parcel_context.html`
- Fan synthesis map: `outputs/maps/phase3_fan_synthesis.html`
- Satellite validation map: `outputs/maps/phase4_satellite_validation.html`
- Canonical parcel boundary: `data/vectors/deanza_villas_complex_boundary.geojson`
- Selected channel network: `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg`
- Parcel overlay metrics: `data/processed/terrain/deanza_villas_2km_1m/parcels/phase3_parcel_overlay_metrics.csv`
- Fan synthesis stats: `data/processed/terrain/deanza_villas_2km_1m/fan_synthesis/phase3_fan_synthesis_stats.csv`
- Satellite validation outputs: `data/processed/terrain/deanza_villas_2km_1m/validation_phase4/phase4_satellite_validation_selected.json`

## Bottom line

The v1 sequence moved from broad-context validation to local 1 m terrain analysis, then to a compact but meaningful wash-network threshold, then to parcel-aware and event-validation checks. The final interpretation remained consistent throughout: De Anza Villas sits in an active alluvial-fan setting with real concentrated-flow exposure and mapped hazard overlap.
