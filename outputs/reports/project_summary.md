# Borrego Springs Flood Study — supporting project summary and file map

## 1) What this project was for

This project built a parcel-focused flood-risk evidence set for De Anza Villas in Borrego Springs, California. The goal was to reconstruct and interrogate the official alluvial-fan flood logic using public data, modern lidar-derived terrain analysis, mapped flood-hazard layers, and satellite surface-water observations.

Why this mattered:
- Borrego Springs sits on coalescing alluvial fans, not a stable valley-floor drainage system.
- Official hazard mapping in this setting is about concentrated flow, sheetflow, avulsion, sediment movement, and changing wash locations.
- The work was designed for practical due diligence: produce evidence layers, maps, and a written summary that help answer whether the parcel sits in active concentrated-flow terrain and how strongly the mapped hazards line up with the terrain signal.

## 2) Sections to follow in this summary

1. Project purpose and scope
2. Data sources and file formats
3. High-level methods and calculations
4. What each workflow step produced and why
5. QGIS project deliverables
6. Key outputs and file locations
7. Limits and interpretation boundaries

## 3) Data sources: where each layer came from

### Core terrain data

| Source | Service / origin | Format used in the project | Why it was used |
|---|---|---:|---|
| Eastern San Diego County 2017 QL2 LiDAR | OpenTopography / NOAA InPort metadata / USGS source dataset | LAS point cloud source, then derived GeoTIFF rasters | Primary analysis-grade elevation source for the Borrego Valley fan surface |
| 1 m DEM derivative | Local terrain processing from the study lidar / reprojection and conditioning | GeoTIFF (`.tif`) | The working surface for slope, accumulation, roughness, and wash extraction |
| Filled DEM | Local derived raster | GeoTIFF (`*_dem_filled.tif`) | Used to remove pits/depressions before flow routing and channel extraction |
| Slope raster | Local derived raster | GeoTIFF (`*_dem_slope_degrees.tif`) | Terrain steepness for parcel and fan-context interpretation |
| D8 flow accumulation raster | Local derived raster | GeoTIFF (`*_dem_d8_flow_accum.tif`) | Used to extract candidate washes/channels and test drainage thresholds |

### Parcel and context geometry

| Source | Service / origin | Format used in the project | Why it was used |
|---|---|---:|---|
| De Anza Villas complex boundary | Local authoritative parcel geometry | GeoJSON | Canonical dissolved boundary for parcel-scale overlay work |
| De Anza Villas parcel polygons | Local parcel set | GeoJSON | Canonical exposure layer for per-parcel review and APN-level labeling |
| 2 km local AOI | Local study geometry | GeoJSON | Small study extent for local terrain and parcel maps |
| 8 km Borrego valley context AOI | Local study geometry | GeoJSON | Wider fan-context reference frame for wash/fan interpretation |

### Flood hazard and regulatory context

| Source | Service / origin | Format used in the project | Why it was used |
|---|---|---:|---|
| FEMA “Know Your Hazards” flood layer for Borrego | FEMA-derived GeoJSON in the repo | GeoJSON | Hazard context overlay for mapped flood polygons |
| FEMA NFHL / county-hosted layers | FEMA NFHL services and county/sanGIS fallbacks discussed in the study | Service-based reference | Used as the official hazard baseline where available |
| Boyle Engineering 1989 flood report | PDF from San Diego County Flood Control archive | PDF | Operative historical basis for Borrego flood-zone logic |
| DRI 2015 active/inactive fan mapping | Conference PDF | PDF | Independent fan-activity interpretation and active/inactive context |
| San Diego County flood protection guidance | County PDF | PDF | Plain-language regulatory interpretation for Borrego Springs |

### Satellite validation data

| Source | Service / origin | Format used in the project | Why it was used |
|---|---|---:|---|
| OPERA DSWx-HLS | NASA PO.DAAC / Earthdata STAC via `earthaccess` | GeoTIFF downloads with browse PNGs when available | Positive evidence of wetting or surface water in the optical record |
| OPERA DSWx-S1 | NASA PO.DAAC / Earthdata STAC via `earthaccess` | GeoTIFF downloads with browse PNGs when available | SAR surface-water check where optical timing or clouds are limiting |

## 4) High-level method: how the calculations were done

### 4.1 Terrain preprocessing and routing

The terrain work used the filled DEM as the routing surface. In broad terms:
- the DEM was conditioned first so flow-routing would not stall in pits/sinks,
- the raster was kept in EPSG:5070 so lengths and areas were interpretable in meters,
- WhiteboxTools was used for D8 routing and channel extraction,
- flow-accumulation threshold sweeps were used to see which network scale best matched the mapped hazard context.

Why this mattered:
- on alluvial fans, the exact wash network is not always a single obvious line;
- the threshold needed to be chosen by comparing the extracted network to known terrain and hazard context, not by blindly accepting one number.

### 4.2 Wash / channel extraction

The channel extraction step used WhiteboxTools and the D8 accumulation raster:
- `extract_streams(...)` was run for several thresholds,
- the stream raster was converted to vector lines,
- line lengths were measured in EPSG:5070,
- each candidate network was intersected with the mapped flood polygons and the AOI polygons,
- the threshold with strong hazard overlap and the most concise geometry among the near-best candidates was selected.

In this project, the practical working threshold that became canonical was 5000 accumulation cells.

What the overlay metrics represented:
- total extracted stream length,
- how much length fell inside the mapped flood polygons,
- how much length fell inside the local AOI and the broader fan-context AOI,
- how many line segments touched the hazard polygons.

### 4.3 Parcel overlay calculations

The parcel overlay step re-ran the same selected stream network against:
- the dissolved De Anza Villas parcel boundary,
- the parcel polygon set,
- the mapped flood polygons.

The main calculations were simple geometry intersections in EPSG:5070:
- stream length inside parcel boundary,
- stream length inside hazard polygons,
- stream length inside both parcel and hazard polygons,
- shares of total stream length for parcel overlap and hazard overlap,
- counts of segments that touched parcel, hazard, or both.

This was done to avoid using a rough hand-drawn footprint when an authoritative parcel boundary already existed.

### 4.4 Fan-activity synthesis

The fan synthesis step combined three things:
- terrain shape from the lidar-derived DEM,
- extracted wash/channel texture from the flow-routing work,
- the official/regulatory fan context from Boyle, DRI, and county/FEMA materials.

It used WhiteboxTools and raster statistics to compute, for the parcel, the local AOI, and the wider fan context:
- elevation minima, maxima, mean, and percentiles,
- relief measures like p95–p5 and max–min,
- slope statistics,
- multiscale roughness statistics,
- stream length and stream density.

The roughness rasters were generated with WhiteboxTools `multiscale_roughness(...)`.

### 4.5 Satellite validation

The satellite step used NASA PO.DAAC / Earthdata access via `earthaccess`.
For each search window:
- candidate OPERA scenes were found by short name and time window,
- each item’s data URL and browse URL were captured,
- the GeoTIFF was downloaded,
- the raster was read pixel-by-pixel,
- water class pixels were counted inside the local AOI and parcel boundary,
- water shares were computed as water pixels divided by valid pixels in each mask.

The key point is that this is evidence of wetting, not a perfect absence test. Sparse overpasses mean a null result does not prove there was no flood.

## 5) What was produced in each workflow step, and why

### Wash extraction — wash / channel extraction

Produced:
- `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.csv`
- `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.json`
- `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg`
- `outputs/reports/wash_extraction.md`
- `outputs/maps/wash_extraction.html`

Why:
- to test multiple channel extraction thresholds,
- to pick a network that matched mapped flood context without being needlessly noisy,
- to create a clean vector network for later parcel and fan-context work.

### Parcel overlay — parcel overlay

Produced:
- `data/processed/terrain/deanza_villas_2km_1m/parcels/parcel_overlay_metrics.csv`
- `data/processed/terrain/deanza_villas_2km_1m/parcels/parcel_overlay_metrics.json`
- `data/processed/terrain/deanza_villas_2km_1m/parcels/deanza_villas_2km_1m_dem_filled_streams_5000_in_parcel.gpkg`
- `outputs/reports/parcel_overlay.md`
- `outputs/maps/parcel_overlay.html`

Why:
- to attach the analysis to the actual parcel boundary,
- to quantify how much of the selected network lies in the complex boundary and mapped hazard polygons,
- to preserve a parcel-specific stream layer for later inspection.

### Fan synthesis — fan synthesis

Produced:
- `data/processed/terrain/deanza_villas_2km_1m/fan_synthesis/fan_synthesis_stats.csv`
- `data/processed/terrain/deanza_villas_2km_1m/fan_synthesis/fan_synthesis_stats.json`
- `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_multiscale_roughness_mag.tif`
- `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_multiscale_roughness_scale.tif`
- `outputs/reports/fan_synthesis.md`
- `outputs/maps/fan_synthesis.html`

Why:
- to summarize parcel vs. local AOI vs. fan-context terrain character,
- to show that the parcel sits in a rugged, active fan drainage fabric,
- to support the interpretation with simple raster statistics rather than an invented flood model.

### Satellite validation — satellite validation

Produced:
- `data/processed/terrain/deanza_villas_2km_1m/satellite_validation/satellite_validation_candidates.csv`
- `data/processed/terrain/deanza_villas_2km_1m/satellite_validation/satellite_validation_candidates.json`
- `data/processed/terrain/deanza_villas_2km_1m/satellite_validation/satellite_validation_selected.json`
- downloaded OPERA scene files in `data/processed/terrain/deanza_villas_2km_1m/satellite_validation/downloads/`
- `outputs/reports/satellite_validation.md`
- `outputs/maps/satellite_validation.html`

Why:
- to check whether satellite products showed positive wetting evidence over the study area,
- to compare optical and SAR-based surface water signals,
- to avoid relying only on terrain interpretation when actual water detections were available.

## 6) QGIS project deliverables

A single QGIS project file was created and refined:
- `deanza-villas-flood-study.qgs`

Why it exists:
- to make the study layers easy to open in a desktop GIS,
- to provide a beginner-friendly starting view instead of a blank canvas,
- to keep the canonical project focused on the study layers with sensible defaults.

High-level QGIS changes:
- project CRS set to EPSG:5070,
- default view extent centered on the study area,
- visible parcel boundary, parcel polygons, stream network, and hazard layers,
- cosmetic styling improvements,
- readable labels for key layers using existing fields only.

## 7) How the geometry and statistics were calculated, at a glance

The main pattern across the workflow steps was consistent:
1. read vectors or rasters from disk,
2. reproject to EPSG:5070,
3. condition the DEM and derive routing rasters,
4. convert extracted drainage rasters to vector lines,
5. intersect linework with parcels, AOIs, and hazard polygons,
6. measure line lengths and ratios in meters,
7. summarize results in CSV and JSON for reproducibility,
8. write markdown reports and HTML maps for review.

In code terms, the heavy lifting came from:
- WhiteboxTools for D8 routing, stream extraction, and multiscale roughness,
- GeoPandas/Shapely for geometry intersections and length calculations,
- Rasterio/NumPy for raster masking and pixel counting,
- Earthaccess for OPERA data discovery and download,
- Folium for the interactive HTML map outputs.

## 8) Why the results are credible, but bounded

This project does not claim a new regulatory flood study. It does claim something narrower and useful:
- the parcel sits on active alluvial-fan terrain,
- the extracted wash/network signal aligns with mapped flood hazard context,
- the parcel-boundary overlay remains substantial after using the authoritative boundary,
- the satellite record adds positive wetting evidence in at least one satellite-validation search window.

What it does not do:
- it does not invent calibrated depth outputs,
- it does not replace FEMA or county engineering determinations,
- it does not claim a full hydraulic model of future flooding.

## 9) Key file locations to browse

Canonical report and maps:
- `outputs/reports/final_report.md`
- `outputs/maps/wash_extraction.html`
- `outputs/maps/parcel_overlay.html`
- `outputs/maps/fan_synthesis.html`
- `outputs/maps/satellite_validation.html`

QGIS project:
- `deanza-villas-flood-study.qgs`

Core study data:
- `data/vectors/deanza_villas_complex_boundary.geojson`
- `data/vectors/deanza_villas_parcel_polygons.geojson`
- `data/raw/fema/oes_know_your_hazards_flooding_borrego.geojson`
- `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_filled.tif`
- `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_slope_degrees.tif`
- `data/processed/terrain/deanza_villas_2km_1m/deanza_villas_2km_1m_dem_d8_flow_accum.tif`
- `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_stream_threshold_sweep.csv`
- `data/processed/terrain/deanza_villas_2km_1m/channels/deanza_villas_2km_1m_dem_filled_streams_5000.gpkg`
- `data/processed/terrain/deanza_villas_2km_1m/parcels/parcel_overlay_metrics.csv`
- `data/processed/terrain/deanza_villas_2km_1m/fan_synthesis/fan_synthesis_stats.csv`
- `data/processed/terrain/deanza_villas_2km_1m/satellite_validation/satellite_validation_candidates.csv`
- `data/processed/terrain/deanza_villas_2km_1m/satellite_validation/satellite_validation_selected.json`

## 10) Bottom line

The project reconstructed a consistent evidence chain from terrain to parcel to satellite validation.
It shows that De Anza Villas is not just near a wash on a map; it sits on an active fan surface with concentrated-flow signals that are consistent across terrain analysis, parcel overlay, and satellite evidence.

That is the core takeaway, and it is why the workflow was built the way it was.
