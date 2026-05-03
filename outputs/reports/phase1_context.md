# Terrain Context Memo: Borrego Springs Flood Hazard Context

## What the terrain context established

The terrain context layer stack now includes the following layers for Borrego Springs:

- Broad study AOI defined: `data/vectors/aoi_borrego_springs.geojson`
- Public source docs archived in `data/raw/docs/`
- County/FEMA-derived flood hazard polygons pulled for the AOI:
  - `data/raw/fema/oes_know_your_hazards_flooding_borrego.geojson`
- First context map generated:
  - `outputs/maps/phase1_context.html`

## Source documents archived

- Boyle / County flood protection guidance: `data/raw/docs/boyle_1989.pdf`
- DRI 2015 alluvial fan mapping presentation: `data/raw/docs/dri_2015_fan_mapping.pdf`
- San Diego County Borrego Springs flood protection guidelines: `data/raw/docs/sd_county_borrego_guidelines.pdf`

Manifest:
- `data/raw/docs/manifest.md`

## FEMA / flood-hazard context

The public San Diego County hazard layer used here is the county-hosted flood hazard polygon service derived from FEMA NFHL.

Layer details from metadata:
- Layer: `Flooding`
- Source: San Diego County / SanGIS layer derived from `NFHL_06073C`
- Latest study effective date: `03/22/2022`
- Latest LOMR effective date: `11/06/2024`
- Coordinate system: EPSG:2230 / NAD 1983 StatePlane California VI feet

AOI query results for the broad Borrego Springs study rectangle:
- Total intersecting flood hazard polygons: `1632`
- Floodplain class counts:
  - `FP100`: `1518`
  - `FW100`: `114`

Interpretation:
- The county/FEMA-derived layer confirms that the Borrego Springs study area sits within a substantial mapped flood hazard environment.
- The presence of floodway polygons within the AOI is important because it means this context is not just about broad SFHA coverage; there are also mapped flow-conveyance constraints to account for later.

## Key document takeaways

### County guidance / Boyle context
- Alluvial fans in Borrego Springs are created by flash floods moving down steep desert canyons.
- Floodwaters can change course and move to a new wash location.
- A design storm flood typically sheets across the fan.
- County guidance states that all areas on the fan are subject to flooding unless appropriate flood protection is provided.
- The named canyon systems include Box, Unnamed, Coyote, El Vado, Henderson, Borrego Palm, Fire, Hellhole, Dry, and Culp-Tubb.

### DRI 2015
- DRI reported that about 90% of the 61 sq mi Borrego Springs study area contains geomorphically and hydraulically active alluvial fan landforms.
- The study generally confirmed the Boyle 1989 flood-hazard delineation.

## What is still missing before parcel work

- Parcel boundary geometry
- Parcel-specific intersection with floodplain / floodway polygons
- Parcel-to-channel distance and vertical separation metrics
- Terrain-derived parcel statistics from lidar / DEM analysis
- Any final property-specific conclusions

## Current status

The terrain context is sufficient to move on to parcel-aware work once the parcel polygon is available.

Recommended next step:
- bring in the parcel boundary and run parcel-scale overlay metrics against the existing AOI and flood hazard context.
