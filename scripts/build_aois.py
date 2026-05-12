"""Build AOI buffers from the canonical parcel boundary.

Generates the two standard analysis extents:
  2km AOI — local terrain analysis (DEM fetch, stream extraction, metrics)
  8km AOI — context mapping and watershed-scale DEM fetch

Both are buffered from the dissolved parcel boundary in EPSG:5070 (meters)
and saved in both EPSG:5070 and WGS84.

Outputs:
  data/derived/vectors/deanza_villas_2km_aoi.geojson
  data/derived/vectors/deanza_villas_2km_aoi_5070.geojson
  data/derived/vectors/borrego_valley_context_8km_aoi.geojson
  data/derived/vectors/borrego_valley_context_8km_aoi_5070.geojson
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd

PROJECT = Path(__file__).resolve().parents[1]

PARCEL = PROJECT / "data" / "raw" / "sangis" / "deanza_villas_complex_boundary.geojson"

OUTPUTS = {
    "2km": {
        "4326": PROJECT / "data" / "derived" / "vectors" / "deanza_villas_2km_aoi.geojson",
        "5070": PROJECT / "data" / "derived" / "vectors" / "deanza_villas_2km_aoi_5070.geojson",
    },
    "8km": {
        "4326": PROJECT / "data" / "derived" / "vectors" / "borrego_valley_context_8km_aoi.geojson",
        "5070": PROJECT / "data" / "derived" / "vectors" / "borrego_valley_context_8km_aoi_5070.geojson",
    },
}

BUFFER_M = {"2km": 2_000, "8km": 8_000}


def main() -> int:
    if not PARCEL.exists():
        print(f"ERROR: Parcel boundary not found: {PARCEL}", file=sys.stderr)
        return 1

    parcel = gpd.read_file(PARCEL)
    parcel_5070 = parcel.to_crs("EPSG:5070")
    parcel_geom = parcel_5070.geometry.iloc[0]

    area_ha = parcel_geom.area / 10000
    center = parcel_5070.geometry.iloc[0].centroid
    print(f"Parcel: {area_ha:.2f} ha, center=({center.x:.0f}, {center.y:.0f}) EPSG:5070")

    for label in ["2km", "8km"]:
        buf_m = BUFFER_M[label]
        buffered = parcel_geom.buffer(buf_m)
        buf_area_ha = buffered.area / 10000
        print(f"\n{label} buffer: +{buf_m}m → {buf_area_ha:.1f} ha")

        gdf_5070 = gpd.GeoDataFrame(
            {"name": [f"De Anza Villas {label} AOI"],
             "buffer_m": [buf_m],
             "area_ha": [round(buf_area_ha, 2)],
             "source_parcel": [str(PARCEL)]},
            geometry=[buffered],
            crs="EPSG:5070",
        )
        gdf_4326 = gdf_5070.to_crs("EPSG:4326")

        for crs_label, crs_gdf, path in [
            ("5070", gdf_5070, OUTPUTS[label]["5070"]),
            ("4326", gdf_4326, OUTPUTS[label]["4326"]),
        ]:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write as proper GeoJSON with CRS metadata
            geojson = json.loads(crs_gdf.to_json())
            geojson["name"] = f"deanza_villas_{label}_aoi"
            if crs_label == "5070":
                geojson["crs"] = {
                    "type": "name",
                    "properties": {"name": "urn:ogc:def:crs:EPSG::5070"},
                }
            with open(path, "w") as f:
                json.dump(geojson, f, indent=2)
            print(f"  EPSG:{crs_label} → {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
