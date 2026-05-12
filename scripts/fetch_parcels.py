"""Fetch De Anza Villas parcel polygons from the SANDAG Parcels_East REST endpoint.

Queries the SANDAG-hosted Parcels_East FeatureServer (public, no API key)
for all parcels with subname matching 'DE ANZA VILLAS%'. The response
includes both De Anza Villas (36 parcels) and Vista Villas (31 parcels,
APN prefix 14026410).

After fetching, run correct_parcel.py to filter Vista Villas and merge
the De Anza blocks into the canonical dissolved boundary.

Endpoint: geo.sandag.org/server/rest/services/Hosted/Parcels_East/FeatureServer/0
CRS: NAD 1983 StatePlane California VI FIPS 0406 Feet (WKID 2230)
Export: GeoJSON (outSR=4326)
Max records: 2000 per query (67 parcels for De Anza — well within limit)
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]

ENDPOINT = (
    "https://geo.sandag.org/server/rest/services/Hosted/"
    "Parcels_East/FeatureServer/0/query"
)

OUTPUT = PROJECT / "data" / "raw" / "sangis" / "deanza_villas_parcel_polygons.geojson"

# Query for all parcels whose subdivision name starts with "DE ANZA VILLAS".
# This returns both De Anza Villas proper and Vista Villas (a sister community
# that shares the subdivision name). correct_parcel.py handles the split.
QUERY_WHERE = "subname LIKE 'DE ANZA VILLAS%'"

# Fields to request. The API returns all fields with outFields=*, but we only
# need identification and geometry. Requesting specific fields keeps the
# payload smaller and avoids churn from assessment-value fields that change
# with each tax roll update.
QUERY_FIELDS = (
    "apn,apn_8,parcelid,subname,submap,"
    "situs_address,situs_street,situs_suffix,situs_community,situs_zip"
)

REQUEST_TIMEOUT = 30


def main() -> int:
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
        req = urllib.request.Request(
            url, headers={"User-Agent": "borrego-flood-study/1.0"}
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 1

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}", file=sys.stderr)
        return 1

    # ArcGIS error-in-body detection
    if "error" in data:
        err = data["error"]
        print(f"ArcGIS error: {err.get('message', err)}", file=sys.stderr)
        return 1

    features = data.get("features", [])
    n = len(features)

    if n == 0:
        print(
            "ERROR: Zero features returned. The subname query may no longer "
            "match, or the SANDAG endpoint may have been reorganized.",
            file=sys.stderr,
        )
        return 1

    # Validate we got the expected mix
    apns = sorted(f["properties"]["apn"] for f in features)
    subnames = set(f["properties"]["subname"] for f in features)

    print(f"Received: {n} features")
    print(f"Subnames: {subnames}")
    print(f"APNs: {apns[0]}...{apns[-1]}")

    # Basic sanity: De Anza Villas should have 60-70 parcels
    if not (60 <= n <= 70):
        print(
            f"WARNING: Unexpected feature count {n} (expected 60-70). "
            "The endpoint may have changed. Review before committing.",
        )

    # Add fetch metadata
    data["metadata"] = {
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
        "source": ENDPOINT,
        "query_where": QUERY_WHERE,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(data, f)
    print(f"Written: {OUTPUT}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
