"""Fetch and derive the De Anza Villas complex boundary from SANDAG source data.

Cache-first: skips the network fetch if raw parcels already exist locally.
To force a re-fetch, delete data/raw/sangis/deanza_villas_parcel_polygons.geojson.

Raw fetch cached at: data/raw/sangis/deanza_villas_parcel_polygons.geojson
Final boundary at:   data/derived/vectors/deanza_villas_complex_boundary.geojson
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from shapely.geometry import mapping

PROJECT = Path(__file__).resolve().parents[1]

ENDPOINT = (
    "https://geo.sandag.org/server/rest/services/Hosted/"
    "Parcels_East/FeatureServer/0/query"
)

RAW_PARCELS = PROJECT / "data" / "raw" / "sangis" / "deanza_villas_parcel_polygons.geojson"
BOUNDARY_OUT = PROJECT / "data" / "derived" / "vectors" / "deanza_villas_complex_boundary.geojson"

QUERY_WHERE = "subname LIKE 'DE ANZA VILLAS%'"
QUERY_FIELDS = (
    "apn,apn_8,parcelid,subname,submap,"
    "situs_address,situs_street,situs_suffix,situs_community,situs_zip"
)
VISTA_APN_PREFIX = "14026410"
BRIDGE_BUFFER_M = 15
REQUEST_TIMEOUT = 30


def _fetch_raw() -> None:
    params = {
        "where": QUERY_WHERE,
        "outFields": QUERY_FIELDS,
        "returnGeometry": "true",
        "f": "geojson",
        "outSR": "4326",
    }
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    print("Querying SANDAG Parcels_East...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "borrego-flood-study/1.0"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {e.code}: {body}")

    data = json.loads(raw)
    if "error" in data:
        raise RuntimeError(f"ArcGIS error: {data['error'].get('message', data['error'])}")

    features = data.get("features", [])
    n = len(features)
    if n == 0:
        raise RuntimeError(
            "Zero features returned — subname query may no longer match "
            "or the SANDAG endpoint may have been reorganized."
        )
    if not (60 <= n <= 70):
        print(f"WARNING: Unexpected feature count {n} (expected 60-70). Review before committing.")

    apns = sorted(f["properties"]["apn"] for f in features)
    subnames = set(f["properties"]["subname"] for f in features)
    print(f"  {n} features, subnames: {subnames}, APNs: {apns[0]}...{apns[-1]}")

    data["metadata"] = {
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
        "source": ENDPOINT,
        "query_where": QUERY_WHERE,
    }
    RAW_PARCELS.parent.mkdir(parents=True, exist_ok=True)
    with open(RAW_PARCELS, "w") as f:
        json.dump(data, f)
    print(f"  Cached: {RAW_PARCELS}")


def main() -> int:
    if RAW_PARCELS.exists():
        print(f"Using cached parcels: {RAW_PARCELS}")
    else:
        _fetch_raw()

    parcels = gpd.read_file(RAW_PARCELS)
    vista_mask = parcels.apn.str.startswith(VISTA_APN_PREFIX)
    deanza = parcels[~vista_mask].copy()
    print(f"De Anza parcels: {len(deanza)} (excluded {vista_mask.sum()} Vista Villas)")

    parcels_5070 = deanza.to_crs("EPSG:5070")
    union = parcels_5070.geometry.union_all()
    result = union.buffer(BRIDGE_BUFFER_M).buffer(-BRIDGE_BUFFER_M)
    print(f"Boundary: {result.area:.0f} m² ({result.area / 10000:.2f} ha)")

    boundary = gpd.GeoDataFrame(geometry=[result], crs="EPSG:5070").to_crs("EPSG:4326").geometry.iloc[0]
    feature = {
        "type": "Feature",
        "properties": {
            "name": "De Anza Villas complex boundary",
            "source": "SanGIS Parcels_East, subname LIKE 'DE ANZA VILLAS%', "
                      "excluding Vista Villas (APN 14026410xx). "
                      "Two blocks merged across Monroe St ROW with morphological close.",
            "parcel_count": len(deanza),
            "excluded_count": int(vista_mask.sum()),
        },
        "geometry": mapping(boundary),
    }
    output = {
        "type": "FeatureCollection",
        "name": "deanza_villas_complex_boundary",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [feature],
    }
    BOUNDARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(BOUNDARY_OUT, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Boundary: {BOUNDARY_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
