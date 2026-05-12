"""Parcel boundary generators.

Each function fetches and derives a single dissolved boundary polygon,
writing it to `output` and returning the path.

Cache-first: raw source data is cached in data/raw/vectors/ and skipped
on subsequent calls. Delete the raw file to force a re-fetch.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon, mapping

_PROJECT = Path(__file__).resolve().parents[1]
_RAW_VECTORS = _PROJECT / "data" / "raw" / "vectors"

_SANDAG_ENDPOINT = (
    "https://geo.sandag.org/server/rest/services/Hosted/"
    "Parcels_East/FeatureServer/0/query"
)
_DEANZA_WHERE = "subname LIKE 'DE ANZA VILLAS%'"
_DEANZA_FIELDS = (
    "apn,apn_8,parcelid,subname,submap,"
    "situs_address,situs_street,situs_suffix,situs_community,situs_zip"
)
_VISTA_APN_PREFIX = "14026410"
_BRIDGE_BUFFER_M = 15


def generate_deanza_villas(
    output: Path = _RAW_VECTORS / "deanza_villas_boundary.geojson",
) -> Path:
    """Fetch and derive the De Anza Villas complex boundary.

    Fetches parcel polygons from SANDAG Parcels_East (cache-first), filters
    out Vista Villas, and merges the two De Anza blocks across Monroe St
    using a morphological close (buffer +15m / -15m).
    """
    output = Path(output)
    raw = _RAW_VECTORS / "deanza_villas_parcel_polygons.geojson"

    if raw.exists():
        print(f"Using cached parcels: {raw}")
    else:
        _fetch_sandag(raw)

    parcels = gpd.read_file(raw)
    vista_mask = parcels.apn.str.startswith(_VISTA_APN_PREFIX)
    deanza = parcels[~vista_mask].copy()
    print(f"De Anza parcels: {len(deanza)} (excluded {vista_mask.sum()} Vista Villas)")

    union = deanza.to_crs("EPSG:5070").geometry.union_all()
    result = union.buffer(_BRIDGE_BUFFER_M).buffer(-_BRIDGE_BUFFER_M)
    print(f"Boundary: {result.area:.0f} m² ({result.area / 10000:.2f} ha)")

    boundary = (
        gpd.GeoDataFrame(geometry=[result], crs="EPSG:5070")
        .to_crs("EPSG:4326")
        .geometry.iloc[0]
    )
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
    geojson = {
        "type": "FeatureCollection",
        "name": output.stem,
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [feature],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(geojson, f, indent=2)
    print(f"Boundary: {output}")
    return output


def _fetch_sandag(dest: Path, timeout: int = 30) -> None:
    params = {
        "where": _DEANZA_WHERE,
        "outFields": _DEANZA_FIELDS,
        "returnGeometry": "true",
        "f": "geojson",
        "outSR": "4326",
    }
    url = _SANDAG_ENDPOINT + "?" + urllib.parse.urlencode(params)
    print("Querying SANDAG Parcels_East...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "borrego-flood-study/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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
        "source": _SANDAG_ENDPOINT,
        "query_where": _DEANZA_WHERE,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w") as f:
        json.dump(data, f)
    print(f"  Cached: {dest}")


# -- OSM / Overpass --

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_DEANZA_CC_WAY_ID = 44500984


def generate_deanza_country_club(
    output: Path = _RAW_VECTORS / "deanza_country_club_boundary.geojson",
) -> Path:
    """Fetch the De Anza Country Club polygon from OpenStreetMap (Overpass API).

    Source: OSM way 44500984. Cache-first — delete output to force re-fetch.
    """
    output = Path(output)
    if output.exists():
        print(f"Using cached boundary: {output}")
        return output

    coords = _fetch_osm_way(_DEANZA_CC_WAY_ID)
    polygon = Polygon(coords)
    area_m2 = (
        gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
        .to_crs("EPSG:5070")
        .geometry.iloc[0]
        .area
    )
    print(f"Boundary: {area_m2:.0f} m² ({area_m2 / 10000:.2f} ha), {len(coords)} nodes")

    feature = {
        "type": "Feature",
        "properties": {
            "name": "De Anza Country Club",
            "source": f"OpenStreetMap way {_DEANZA_CC_WAY_ID}",
        },
        "geometry": mapping(polygon),
    }
    geojson = {
        "type": "FeatureCollection",
        "name": output.stem,
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [feature],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(geojson, f, indent=2)
    print(f"Boundary: {output}")
    return output


def _fetch_osm_way(way_id: int, timeout: int = 30) -> list[tuple[float, float]]:
    """Fetch an OSM way polygon from Overpass. Returns (lon, lat) coordinate list."""
    query = f"[out:json];way({way_id});out geom;"
    req = urllib.request.Request(
        _OVERPASS_URL,
        data=query.encode(),
        headers={"User-Agent": "borrego-flood-study/1.0", "Content-Type": "text/plain"},
    )
    print(f"Querying Overpass for OSM way {way_id}...")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)

    elements = data.get("elements", [])
    if not elements:
        raise RuntimeError(f"Overpass returned no elements for way {way_id}")

    nodes = elements[0].get("geometry", [])
    if not nodes:
        raise RuntimeError(f"Way {way_id} has no geometry — try 'out geom' query")

    return [(n["lon"], n["lat"]) for n in nodes]
