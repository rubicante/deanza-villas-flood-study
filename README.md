# Borrego Springs Alluvial Fan Flood Risk Study

A terrain-driven flood risk assessment for Borrego Springs, California, using open-source
geospatial Python tools. The goal is to independently reconstruct, test, and extend the
parcel-scale logic behind official alluvial fan flood studies using public data, modern
lidar, reproducible terrain analysis, and satellite observations.

This project treats the official regulatory work as something that can be interrogated,
replicated where source data allows, and improved for parcel-level due diligence. The
standard is practical decision support: produce maps, evidence layers, and a written
assessment strong enough to guide property risk judgment and to challenge vague or
unsupported flood-risk claims.

Current working docs:
- `outputs/reports/final_report.md` — canonical final narrative
- `TODO.md` — queued work for the current effort
- `DEVLOG.md` — rolling active log

---

## Project Feasibility (validated May 2026)

Verdict: feasible. The available public data and open-source tooling are sufficient to
build a serious independent flood-risk assessment for Borrego Springs alluvial fan
hazards. The project can reproduce the key regulatory context, derive modern terrain
metrics from analysis-grade lidar, compare parcel-scale conditions to FEMA/Boyle/DRI
hazard evidence, and produce defensible maps for property-level judgment.

Core project outputs:
  - Acquire analysis-grade lidar for the Borrego Valley alluvial fan surface.
  - Reconstruct the official hazard picture from FEMA NFHL, the Boyle 1989 flood hazard
    map, San Diego County guidance, and the DRI active/inactive fan interpretation.
  - Derive parcel-scale terrain indices: slope, local relief, curvature, flow accumulation,
    relative elevation, channel/wash proximity, and flow-path concentration.
  - Compare the target parcel against mapped AO zones, depth/velocity evidence, fan
    activity, extracted drainage patterns, and observed surface-water detections.
  - Produce interactive maps and a written risk assessment suitable for practical property
    due diligence.

Validated constraints to solve during the project:
  - Georeferencing the Boyle 1989 PDF depth/velocity map may be necessary unless source
    GIS contours are found.
  - Reconstructing DRI 2015 active/inactive fan polygons may require locating county GIS
    deliverables or digitizing/georeferencing public figures.
  - OPERA DSWx can provide useful positive evidence of surface water, but missed detections
    are expected because desert flash flooding is short-lived and satellite sampling is
    sparse.

Modeling posture: use multiple terrain and evidence layers rather than betting the entire
analysis on one synthetic flood-depth raster. HAND is included as a relative elevation
and drainage-position index, not as the only measure of inundation. For active alluvial
fans, the flood problem is not just water depth in a fixed channel; it is flow-path
concentration, fan activity, sediment movement, erosion/deposition, and avulsion risk.

## Study Area & Hazard Context

Borrego Springs sits in the Borrego Valley, a closed desert basin in eastern San Diego
County (~580 ft elevation, ~33.26°N 116.37°W). The valley floor is almost entirely
covered by coalescing alluvial fans fed by roughly 10 named canyon systems draining the
Santa Rosa and San Ysidro Mountains:

  Box Canyon, Unnamed Canyon, Coyote Canyon, El Vado Canyon, Henderson Canyon,
  Borrego Palm Canyon, Fire Canyon, Hellhole Canyon, Dry Canyon, Culp-Tubb Canyon complex

The 2015 Desert Research Institute mapping study found that 90% of the 61 sq mi study
area contains geomorphically and hydraulically active alluvial fan landforms. This is
the baseline hazard reality: nearly the entire valley floor is an active depositional
system subject to sudden flow path changes.

FEMA designates most of Borrego Springs as Zone AO on FIRM panels -- Special Flood
Hazard Areas subject to 1% annual chance (100-year) sheet-type flow. Critically, AO
zones here carry both depth numbers (1 to >3 ft) AND velocity hazards. Flash floods
from the canyons routinely exceed existing wash capacity, sheet-flow across the fan,
and establish new wash locations. There is no stable "safe" channel alignment.

Key regulatory baseline: San Diego County adopted the Boyle Engineering 1989 Borrego
Valley Flood Management Report on October 17, 1989. FEMA still uses it as the basis
for flood insurance risk zone assignments in the valley. The 2015 DRI study generally
confirmed Boyle's delineation -- the hazard picture hasn't materially changed.

---

## Primary Source Documents

### Boyle Engineering (1989) — Borrego Valley Flood Management Report
Accepted by SD County Board of Supervisors Oct 17, 1989. Mapped depth-velocity contours
for alluvial fans from all 10 canyon sources listed above. Still the operative FEMA
engineering basis for AO zone assignments. Flood Hazard Map PDF:
  https://www.sdcfcd.org/content/dam/sdc/sdcfcd/doc/maps/brgofans.pdf

### Desert Research Institute (2015) — Active/Inactive Alluvial Fan Mapping
Conducted for San Diego County. Classified fan surfaces as geomorphically active vs.
inactive using aerial photo interpretation, field verification, and soil/geomorphic
criteria per FEMA Appendix G. Key finding: 90% of 61 sq mi study area is active.
Generally confirmed Boyle 1989 delineation. Conference presentation PDF:
  https://cdn.ymaws.com/floodplain.org/resource/resmgr/2015Conference/Wednesday/Borrego-Springs-Alluvial-Fan.pdf

### FEMA Guidance — Alluvial Fan Flood Risk Analysis (November 2016)
Methodological reference for risk-based analysis, FAN computer program, sheetflow
analysis, and geomorphic data methods. Relevant for understanding how official analyses
are structured and what defensibility requires:
  https://www.fema.gov/sites/default/files/2020-02/Alluvial_Fans_Guidance_Nov_2016.pdf

### San Diego County — Guidelines for Flood Protection in Borrego Springs
Plain-language summary of regulatory requirements: BFE elevation, mechanical equipment
elevation, drainage path requirements, no-deflection rule. Good for interpreting what
the FIRM depth numbers mean at the parcel level:
  https://www.sandiegocounty.gov/content/dam/sdc/dpw/FLOOD_CONTROL/floodcontroldocuments/Guidelines%20for%20Flood%20Protection%20of%20Structures%20in%20Borrego%20Springs.pdf

---

## Elevation Data

### Primary: Eastern San Diego County, California 2017 QL2 LiDAR
Validated source: NOAA InPort item 54015 and OpenTopography dataset
`USGS_LPC_CA_E_SanDiegoCo_2016_LAS_2017`.

Important facts:
  - Classified LAS 1.4 point cloud, 1,710 tiles, each 5,000 ft x 5,000 ft.
  - Collection dates: 2016-10-31 to 2017-01-31.
  - Nominal pulse spacing: ~0.67-0.7 m; point density roughly 2.26-3.70 pts/m2.
  - Projection/datum: NAD83(2011), State Plane California Zone VI, US survey feet;
    vertical datum NAVD88 GEOID12B, US survey feet.
  - Derived products include hydro-flattened DEMs with 2.5 ft cell size, breaklines,
    contours, building footprints, and classified ground points.
  - Coverage bounds include Borrego Valley: west -117.5185, east -116.0752,
    north 33.5073, south 32.5915.

Preferred access path:
  1. Use OpenTopography dataset page/API to subset and grid the point cloud for the
     parcel/AOI plus upstream contributing fan area.
  2. If OpenTopography API friction appears, use USGS AWS public/requester-pays lidar
     tiles or manual LidarExplorer download.
  3. Use py3dep for fast preliminary 1 m DEM fetches and prototype notebooks, but do
     not assume py3dep gives the exact original 2.5 ft hydro-flattened source DEM.

OpenTopography dataset:
  https://portal.opentopography.org/usgsDataset?dsid=USGS_LPC_CA_E_SanDiegoCo_2016_LAS_2017

NOAA metadata:
  https://www.fisheries.noaa.gov/inport/item/54015

USGS LidarExplorer:
  https://apps.nationalmap.gov/lidar-explorer/

### Reference: SANDAG Regional DEM (ArcGIS ImageServer)
Merged mosaic of 2014, 2015, and 2017 QL2 acquisitions at 2.5 ft pixel size. Borrego
Valley DEM was merged first (highest priority in mosaic). Accessible as ArcGIS REST:
  https://gis.sandag.org/sdgis/rest/services/Elevation/SanDiego_Regional_DEM/ImageServer

IMPORTANT CAVEAT: SANDAG's own documentation states this merged DEM is "adequate for
cartographic purposes" only. For analysis, use the original source data from each
project. We use the SANDAG service for quick visualization, bounding-box checks, and
sanity comparisons, not as the quantitative source of record.

### FEMA NFHL and local regulatory layers
Use FEMA National Flood Hazard Layer (NFHL) services for current effective AO flood
zones, FIRM panel references, and depth attributes where available. Do not assume NFHL
will expose all Boyle depth/velocity contour detail; if velocity/depth contours are only
available in the Boyle PDF, they must be georeferenced or manually digitized with an
uncertainty note.

FEMA NFHL overview and services:
  https://www.fema.gov/flood-maps/national-flood-hazard-layer
  https://hazards.fema.gov/femaportal/wps/portal/NFHLWMS

### Satellite / SAR Validation
OPERA DSWx-HLS (Harmonized Landsat/Sentinel-2 optical) and DSWx-S1 (Sentinel-1 SAR)
products are analysis-ready GeoTIFFs distributed through NASA PO.DAAC / Earthdata. They
map pixel-wise surface water detections at 30 m posting. These are useful validation
layers, but not definitive proof of absence of flooding because desert flash floods may
be short-lived and missed by satellite overpass timing.

---

## Analysis Approach

### Terrain context — reproduce the official/regulatory setting
  1. Fetch FEMA NFHL AO polygons and attributes for Borrego Springs.
  2. Download and archive the Boyle 1989 flood hazard PDF and County guideline PDF.
  3. Attempt to locate source GIS for Boyle contours and DRI active/inactive polygons.
  4. If source GIS is unavailable, georeference/digitize PDF figures with explicit
     uncertainty classes: high confidence near control points, lower confidence elsewhere.

### Wash extraction and parcel-scale terrain analysis (whitebox-tools + rasterio)
These tools do the core quantitative work: translate lidar into reproducible terrain
metrics that can be compared directly against mapped regulatory hazards and parcel
conditions.
  1. DEM preprocessing: reproject, clip to AOI plus upstream fan, breach/fill depressions.
  2. Slope, curvature, local relief, and roughness.
  3. D8 and, where possible, multi-flow-direction accumulation to test sensitivity.
  4. Wash/channel extraction using multiple accumulation thresholds.
  5. Flow-path concentration and parcel crossing analysis.
  6. Relative elevation / HAND as one terrain index among several.
  7. Distance and vertical separation from mapped washes, extracted channels, and AO
     depth/velocity contours.

### Fan activity and evidence synthesis
Use FEMA's three-stage alluvial fan framing:
  - Stage 1: confirm fan landform, composition, morphology, and mountain-front location.
  - Stage 2: compare active/inactive geomorphic evidence from DRI, aerial imagery,
    wash density, channel freshness, relative relief, and surface roughness.
  - Stage 3: characterize 1-percent-annual-chance severity using FEMA/Boyle/NFHL data;
    do not independently claim calibrated depth or velocity.

### Satellite/event validation
Use GeoAgent, earthaccess, pystac-client, or direct PO.DAAC STAC calls to retrieve:
  - OPERA DSWx-HLS: optical surface water, cloud-limited, 30 m.
  - OPERA DSWx-S1: SAR surface water/inundated vegetation, 30 m.
  - Sentinel-1 GRD scenes for custom backscatter checks if OPERA coverage is sparse.

Validation target: look for positive evidence of historical wetting or flow concentration.
Absence of DSWx water is weak evidence because of temporal sampling limitations.

Progress note: satellite validation has been completed; see outputs/reports/satellite_validation.md and outputs/maps/satellite_validation.html.

### Visualization (leafmap)
Interactive HTML maps overlaying: terrain indices, channel extraction, HAND, Boyle 1989
contours if georeferenced, DRI 2015 active/inactive interpretation if obtained/digitized,
FEMA NFHL AO zones, OPERA surface water detections, parcel boundaries from SanGIS/SANDAG.

### Project Boundaries
- Build a practical property-risk assessment from public regulatory evidence, lidar terrain
  reconstruction, geomorphic fan activity, and observed water detections.
- Use FEMA/Boyle/DRI materials as the benchmark to reproduce and interrogate.
- Do not present outputs as a stamped engineering report, legal flood-zone determination,
  or FEMA map revision unless a licensed professional later adopts and extends the work.
- Treat safety claims conservatively: the study can rank and explain risk, but final
  construction/permitting decisions still require the applicable professional process.

---

## Repository Structure

    deanza-villas-flood-study/
    ├── README.md               -- this file
    ├── AGENTS.md               -- agent entry point
    ├── DEVLOG.md               -- rolling development log
    ├── TODO.md                 -- queued work backlog
    ├── config/                 -- study.yaml, study_manifest.yaml
    ├── data/
    │   ├── raw/                -- downloaded DEMs, FIRM panels, source PDFs
    │   ├── processed/          -- clipped/reprojected rasters, derived products
    │   └── vectors/            -- AOI boundary, parcel, fan polygon layers
    ├── scripts/                -- pipeline orchestrator and workflow scripts
    └── outputs/
        ├── maps/               -- exported leafmap HTML files
        └── reports/            -- summary tables, risk assessments

---

## Tooling & Connectors

### NASA Earthdata (required for OPERA DSWx)
OPERA surface water products live on NASA PO.DAAC behind Earthdata auth. Free account
required at https://urs.earthdata.nasa.gov. Store Earthdata credentials in the project-local
.env alongside the OpenTopography key:

    OPEN_TOPOGRAPHY_API_KEY=YOUR_OPENTOPOGRAPHY_KEY
    EARTHDATA_USERNAME=YOUR_USERNAME
    EARTHDATA_PASSWORD=YOUR_PASSWORD

Also plan to use the Python `earthaccess` package for token/session handling.

### py3dep (fast preliminary DEM access, no key needed)
Python client for the USGS 3DEP Web Coverage Service. Fetches DEMs programmatically by
bounding box and can request 1 m coverage where available. Use it for quick prototypes,
AOI checks, and sanity comparisons. For final products, prefer the specific 2017 QL2
source lidar / DEM from OpenTopography or USGS tiles.
https://github.com/hyriver/py3dep

### OpenTopography API (preferred high-resolution lidar subset path)
REST API for programmatic access to the exact Eastern San Diego 2017 QL2 point cloud
and derived 1 m / custom DEM products. Free account/API key may be required depending
on current access policy and request type.
https://portal.opentopography.org

### FEMA NFHL services
Use FEMA's WMS/REST/geodatabase access for current effective flood hazard polygons.
These layers are the regulatory baseline, but may not contain every Boyle 1989 velocity
or depth contour needed for local interpretation.

### GeoAgent (optional connector, not required analysis engine)
GeoAgent is useful if its STAC/NASA OPERA wrappers reduce boilerplate, but it is not
required. The same retrieval can be done with `earthaccess`, `pystac-client`, and direct
PO.DAAC links. The hydrology analysis remains whitebox-tools/rasterio/geopandas.

### Jupyter Live Kernel (working mode for analysis)
All quantitative analysis should run in a persistent Jupyter kernel rather than only
standalone scripts. Geospatial work is inherently iterative -- raster output drives
threshold choices which drive re-runs. The hermes jupyter-live-kernel skill manages the
kernel lifecycle and lets the agent call cells interactively.

---

## Key References (additional)

- FEMA NFIP: Zone AO definition and CFR Part 60.3 construction requirements
- National Research Council (1996): Alluvial Fan Flooding (conceptual framework)
- FEMA NFHL: https://www.fema.gov/flood-maps/national-flood-hazard-layer
- NOAA InPort Eastern San Diego QL2 lidar: https://www.fisheries.noaa.gov/inport/item/54015
- OpenTopography Eastern San Diego 2017 QL2: https://portal.opentopography.org/usgsDataset?dsid=USGS_LPC_CA_E_SanDiegoCo_2016_LAS_2017
- SanGIS parcel/flood layers: https://www.sangis.org
- py3dep (USGS 3DEP Python client): https://github.com/hyriver/py3dep
- earthaccess (NASA Earthdata Python): https://github.com/nsidc/earthaccess
- whitebox-tools: https://www.whiteboxgeo.com/manual/wbt_book/
- opengeos/GeoAgent: https://github.com/opengeos/GeoAgent
- leafmap: https://leafmap.org
