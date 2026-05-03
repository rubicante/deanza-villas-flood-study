# Phase 3 Fan Activity / Evidence Synthesis

This phase synthesizes the Borrego Springs fan-activity evidence from the official flood-protection documents and the 1 m De Anza Villas terrain derivatives.

## Source-document signal

- DRI 2015 active/inactive fan mapping: the Borrego Springs study area is dominated by active alluvial-fan landforms; the working summary used in this project is that about 90% of the 61 sq mi study area is geomorphically and hydraulically active.
- Boyle / County guidance: flash floods move rapidly down desert canyons, smaller flows occupy existing washes until they are obstructed or aggrade, design-storm floods can sheet-flow across the fan and establish new washes, and all fan areas are subject to flooding unless properly protected.
- County guidance also flags fan-terminus washes and local washes as flow-concentrating features that often need additional engineering analysis.

## Terrain evidence from the 1 m DEM

```csv
area_name,area_m2,area_km2,valid_cells,elev_min,elev_p5,elev_mean,elev_p95,elev_max,elev_std,relief_p95_p5_m,relief_max_min_m,slope_mean_deg,slope_p95_deg,slope_std_deg,rough_mean_m,rough_p95_m,rough_std_m,stream_length_m,stream_density_m_per_km2
parcel,80361.23210044966,0.08036123210044967,113887,190.07951239941121,190.84456787109374,196.2625139555318,219.82375793457032,252.7658233642578,9.325514479189728,28.97919006347658,62.6863109648466,7.28884775470071,37.355849456787105,12.064183245625456,3.58631076309747,9.570520210266112,2.6560881560573995,904.6317674215298,11257.066918669952
local_aoi,1165690.3146976982,1.1656903146976982,1651993,188.7411706435546,190.2078036718749,234.37227111710067,390.8969665527343,467.99676513671875,67.35464423378131,200.68916288085939,279.25559449316415,14.061292505805545,40.543540191650386,15.047939257741481,5.113133688829117,11.19108543395996,3.383960764711387,19706.975439186906,16905.841277661788
context_aoi,18680569.91550477,18.68056991550477,2987670,188.27378845214844,190.3086311340332,242.00068359430998,423.80158996582026,494.1436767578125,75.48224439190871,233.49295883178706,305.86988830566406,14.314819603806704,40.76827621459961,15.239156102600884,5.205644964010405,11.802611923217771,3.6022027131746412,31848.432512341642,1704.896191946886
```

Interpretation:
- The local 2 km AOI has a p95-p5 elevation relief of 200.7 m, mean slope of 14.1°, and mean multiscale roughness of 5.1 m.
- The De Anza Villas parcel boundary itself still carries 29.0 m of p95-p5 relief, mean slope of 7.3°, and mean roughness of 3.6 m.
- The broader fan context AOI remains rugged: p95-p5 relief 233.5 m, mean slope 14.3°, mean roughness 5.2 m.

## Wash / channel texture

- Selected 5000-cell channel network length inside the parcel boundary: 904.6 m.
- Parcel-length hazard overlap: 875.2 m (96.7% of parcel-crossing channel length).
- Parcel stream density: 11257.1 m/km², versus 1704.9 m/km² across the 8 km fan context AOI.
- The local 2 km AOI has 16905.8 m/km², consistent with a concentrated drainage belt near the mountain-front/fan-transition area.

## Fan-activity synthesis

- Stage 1 — landform confirmation: Borrego Springs sits on coalescing alluvial fans fed by canyon systems; the parcel is on the fan surface, not an isolated benign upland.
- Stage 2 — geomorphic activity: the DRI mapping and the dense, branching extracted wash network both support active-fan behavior rather than stable, fixed-drainage behavior.
- Stage 3 — flood severity context: Boyle/County/FEMA context remains severe; the regulatory guidance treats the fan as flood-prone and acknowledges avulsion / new-wash formation risk.
- Overall: the parcel sits within an active fan drainage fabric. The right reading is concentrated-flow exposure with channel mobility, not a one-time fixed-channel problem.

## Outputs

- Phase 3 report: `outputs/reports/phase3_fan_synthesis.md`
- Phase 3 map: `outputs/maps/phase3_fan_synthesis.html`
- Terrain stats CSV: `data/processed/terrain/deanza_villas_2km_1m/fan_synthesis/phase3_fan_synthesis_stats.csv`
- Terrain stats JSON: `data/processed/terrain/deanza_villas_2km_1m/fan_synthesis/phase3_fan_synthesis_stats.json`
- Roughness magnitude raster: `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_multiscale_roughness_mag.tif`
- Roughness scale raster: `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_multiscale_roughness_scale.tif`
- Parcel overlay metrics used here: `data/processed/terrain/deanza_villas_2km_1m/parcels/phase3_parcel_overlay_metrics.csv`
- Parcel boundary: `data/vectors/deanza_villas_complex_boundary.geojson`
- Parcel polygons: `data/vectors/deanza_villas_parcel_polygons.geojson`
- Local AOI: `data/vectors/deanza_villas_2km_aoi.geojson`
- Context AOI: `data/vectors/borrego_valley_context_8km_aoi.geojson`
- Hazard polygons: `data/raw/fema/oes_know_your_hazards_flooding_borrego.geojson`
- Selected channel network: `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg`

## Caveat

These are evidence-synthesis outputs from public documents and terrain analysis, not a stamped engineering flood report or FEMA map revision.
