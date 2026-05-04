# DRI 2015 fan-zone roughness comparison

## What was produced
- Source PDF: `data/raw/dri_2015_borrego_fans.pdf`
- Rendered page 20: `data/processed/dri_2015/dri_page_20_300dpi.png`
- QC overlay: `data/processed/dri_2015/dri_page_20_class_masks_on_map.png`
- Digitized fan zones, EPSG:4326: `data/vectors/dri_2015_fan_zones.geojson`
- Reprojected fan zones, EPSG:5070: `data/vectors/dri_2015_fan_zones_epsg5070.geojson`
- Machine-readable stats: `data/processed/terrain/deanza_villas_2km_1m/dri_roughness_comparison_stats.json`

## Method summary
Page 20 of the DRI 2015 presentation was rendered at 300 dpi. The visible latitude/longitude graticule was used to fit a simple affine transform in EPSG:4326, then the DRI pink active-fan and green inactive-fan fills were color-classified from the map image. The inset legend was masked out before polygonization. The resulting broad polygons were saved and reprojected to EPSG:5070 for raster comparison.

Digitization confidence: moderate for broad active/inactive extents; low-moderate for small inactive polygons, boundaries, and map-collar/annotation-adjacent details. This is a reproducible first-pass digitization from a PDF map, not an authoritative source GIS layer.

## Parcel overlap with DRI classes
- Parcel area: 80361.2 m²
- Active overlap: 80040.7 m² (99.60%)
- Inactive overlap: 0.0 m² (0.00%)

## Roughness magnitude benchmarks
| Zone | Count | Mean (m) | Std (m) | P10 | Median | P90 |
|---|---:|---:|---:|---:|---:|---:|
| active | 2,074,005 | 3.754 | 2.906 | 1.387 | 2.527 | 8.460 |
| inactive | 0 | n/a | n/a | n/a | n/a | n/a |
| parcel | 113,887 | 3.586 | 2.656 | 1.378 | 2.584 | 8.088 |

## Roughness scale benchmarks
| Zone | Count | Mean (m) | Std (m) | P10 | Median | P90 |
|---|---:|---:|---:|---:|---:|---:|
| active | 2,074,005 | 16.719 | 5.748 | 6.000 | 21.000 | 21.000 |
| inactive | 0 | n/a | n/a | n/a | n/a | n/a |
| parcel | 113,887 | 17.747 | 5.168 | 6.000 | 21.000 | 21.000 |

## Interpretation
- The active/inactive benchmark could not be fully computed because one class did not overlap the local roughness raster after digitization.
- The parcel mean roughness is 3.586 m. Compare this against the active/inactive means above as a local benchmark, not a calibrated flood-depth or regulatory hazard metric.
- The DRI overlay is useful as independent geomorphic context. It should not be treated as a replacement for FEMA alluvial-fan flood hazard mapping or a hydraulic model.

## Georeferencing diagnostics
- Render DPI: 300.0
- Image size: 4000 x 2250 px
- Max longitude fit residual: 0.00000000°
- Max latitude fit residual: 0.00000000°
- Classified active pixels: 815,110
- Classified inactive pixels: 17,380
