# DRI 2015 fan-zone roughness comparison

## What was produced
- Source PDF: `data/raw/dri_2015_borrego_fans.pdf`
- Rendered page 20: `data/raw/manual/dri_page_20_300dpi.png`
- QC overlay: `data/raw/manual/dri_page_20_class_masks_on_map.png`
- Digitized fan zones, EPSG:4326: `data/derived/vectors/dri_2015_fan_zones.geojson`
- Reprojected fan zones, EPSG:5070: `data/derived/vectors/dri_2015_fan_zones_epsg5070.geojson`
- Machine-readable stats: `data/derived/2km_aoi/dri_roughness_comparison_stats.json`

## Method summary
Page 20 of the DRI 2015 presentation was rendered at 300 dpi. The visible latitude/longitude graticule was used to fit a simple affine transform in EPSG:4326, then the DRI pink active-fan and green inactive-fan fills were color-classified from the map image. The inset legend was masked out before polygonization. The resulting broad polygons were saved and reprojected to EPSG:5070 for raster comparison.

Digitization confidence: moderate for broad active/inactive extents; low-moderate for small inactive polygons, boundaries, and map-collar/annotation-adjacent details. This is a reproducible first-pass digitization from a PDF map, not an authoritative source GIS layer.

## Parcel overlap with DRI classes
- Parcel area: 50646.6 m²
- Active overlap: 50326.1 m² (99.37%)
- Inactive overlap: 0.0 m² (0.00%)

## Roughness magnitude benchmarks
| Zone | Count | Mean (m) | Std (m) | P10 | Median | P90 |
|---|---:|---:|---:|---:|---:|---:|
| active | 2,074,005 | 3.754 | 2.906 | 1.387 | 2.527 | 8.460 |
| inactive | 0 | n/a | n/a | n/a | n/a | n/a |
| parcel | 71,779 | 4.465 | 3.100 | 1.481 | 3.031 | 9.208 |

## Roughness scale benchmarks
| Zone | Count | Mean (m) | Std (m) | P10 | Median | P90 |
|---|---:|---:|---:|---:|---:|---:|
| active | 2,074,005 | 16.719 | 5.748 | 6.000 | 21.000 | 21.000 |
| inactive | 0 | n/a | n/a | n/a | n/a | n/a |
| parcel | 71,779 | 17.676 | 5.398 | 6.000 | 21.000 | 21.000 |

## Interpretation
- The active/inactive benchmark could not be fully computed because one class did not overlap the local roughness raster after digitization.
- The parcel mean roughness is 4.465 m. Compare this against the active/inactive means above as a local benchmark, not a calibrated flood-depth or regulatory hazard metric.
- The DRI overlay is useful as independent geomorphic context. It should not be treated as a replacement for FEMA alluvial-fan flood hazard mapping or a hydraulic model.

## Georeferencing diagnostics
- Render DPI: 300.0
- Image size: 4000 x 2250 px
- Max longitude fit residual: 0.00000000°
- Max latitude fit residual: 0.00000000°
- Classified active pixels: 815,110
- Classified inactive pixels: 17,380
