"""Fetch FEMA NFHL flood hazard data for the Borrego Valley study area.

Queries the California NFHL Reduced Set (ArcGIS REST) for DFIRM 06073C
within 8 km of the De Anza Villas parcel center. Validates the response
against expected feature count, field schema, geometry type, and total
area before writing the canonical output.

Endpoint: services2.arcgis.com CA reduced set
Source: Derived from November 29, 2023 FEMA NFHL S_FLD_HAZ_AR for California.
        See references/fema-nfhl-data-access.md for alternatives.

The query is parameterized by the parcel boundary — not hardcoded to
Borrego Springs coordinates — so it works for any study area with a
committed parcel GeoJSON.

=== Canonical-file currency ===

On each run this script compares the live endpoint response against the
committed canonical file (if it exists) and reports differences. Three
outcomes:

1. IDENTICAL — response matches canonical. Nothing to do.
2. ENDPOINT CHANGED BUT FILE IS AUTHORITATIVE — field names, feature
   count, or geometry shifted upstream but the committed file is still the
   correct study reference. Update the validation constants in this script
   to match the new endpoint shape, then re-run.
3. FILE IS STALE — the endpoint has newer flood data (revised zones,
   updated depth/velocity values, different effective date). Replace the
   canonical file with the new response, commit with a note about the
   revision date, and update the validation constants.

Which case you're in matters — do not blindly overwrite the canonical
file. The script defaults to dry-run (reports differences but does not
write). Pass --write to update the canonical file.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- Configurable constants ---
# These are validated on every run. If the endpoint shape changes,
# update these to match the new response before accepting output.
EXPECTED_FEATURE_COUNT_RANGE = (30, 60)  # spatially filtered DFIRM 06073C
EXPECTED_ZONES = frozenset({"AO", "A", "X", "AE", "D", "AH", "VE", "OPEN WATER",
                             "0.2 PCT ANNUAL CHANCE FLOOD HAZARD"})
REQUIRED_FIELDS = frozenset({
    "DFIRM_ID", "FLD_ZONE", "ZONE_SUBTY", "SFHA_TF",
    "STATIC_BFE", "V_DATUM", "DEPTH", "LEN_UNIT",
    "VELOCITY", "VEL_UNIT", "SOURCE_CIT",
})
EXPECTED_GEOMETRY_TYPE = "Polygon"
EXPECTED_TOTAL_AREA_KM2_RANGE = (0.5, 500)  # 8km buffer around parcel
SEARCH_RADIUS_M = 8_000
TARGET_DFIRM = "06073C"

# ArcGIS REST endpoint (CA NFHL Reduced Set — only endpoint confirmed working
# from this server as of May 2026)
ENDPOINT = (
    "https://services2.arcgis.com/Uq9r85Potqm3MfRV/arcgis/rest/services/"
    "S_FLD_HAZ_AR_Reduced_Set_CA_wm/FeatureServer/0/query"
)

PROJECT = Path(__file__).resolve().parents[1]
PARCEL = PROJECT / "data" / "raw" / "sangis" / "deanza_villas_complex_boundary.geojson"
OUTPUT = PROJECT / "data" / "raw" / "fema" / "nfhl_borrego_valley.geojson"
REQUEST_TIMEOUT = 30
MAX_REDIRECTS = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parcel_center(parcel_path: Path) -> tuple[float, float]:
    """Return (lon, lat) centroid of the parcel boundary."""
    import geopandas as gpd
    gdf = gpd.read_file(parcel_path)
    if len(gdf) == 0:
        raise RuntimeError(f"No features in parcel file: {parcel_path}")
    centroid = gdf.geometry.union_all().centroid
    return (centroid.x, centroid.y)


def _request_json(url: str, timeout: int = REQUEST_TIMEOUT) -> dict[str, Any]:
    """GET a URL and return parsed JSON. Raises on HTTP error, empty body,
    or JSON parse failure."""
    req = urllib.request.Request(url, headers={"User-Agent": "borrego-flood-study/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(
            f"HTTP {e.code} from ArcGIS REST:\n{body}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Request failed: {e}") from e

    if not raw.strip():
        raise RuntimeError("Empty response body from ArcGIS REST")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        preview = raw[:500].decode("utf-8", errors="replace")
        raise RuntimeError(f"JSON parse error: {e}\nFirst 500 bytes:\n{preview}") from e

    return data


def _query_dfirm(lon: float, lat: float) -> dict[str, Any]:
    """Query the CA NFHL Reduced Set for DFIRM 06073C within SEARCH_RADIUS_M
    of the given point."""
    params = {
        "where": f"DFIRM_ID='{TARGET_DFIRM}'",
        "outFields": "*",
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": str(SEARCH_RADIUS_M),
        "units": "esriSRUnit_Meter",
        "returnGeometry": "true",
        "f": "geojson",
        "outSR": "4326",
    }
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    return _request_json(url)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_response(data: dict[str, Any], lon: float, lat: float) -> list[str]:
    """Validate the ArcGIS REST response. Returns a list of warning/error
    messages (empty list = all gates pass).

    Gates:
    1. No ArcGIS error-in-body
    2. Feature count in expected range
    3. All expected fields present
    4. Geometry type matches expectation
    5. Total area in expected range
    6. All FLD_ZONE values are recognized
    7. DFIRM_ID matches target
    """
    issues: list[str] = []

    # Gate 1: ArcGIS error-in-body (returns 200 with error JSON)
    if "error" in data:
        err = data["error"]
        msg = err.get("message", str(err))
        issues.append(f"ArcGIS error in response body: {msg}")
        return issues  # remaining gates are meaningless

    features = data.get("features")
    if features is None:
        issues.append("Response missing 'features' key (not valid GeoJSON)")
        return issues

    n = len(features)

    # Gate 2: Feature count
    lo, hi = EXPECTED_FEATURE_COUNT_RANGE
    if n < lo:
        issues.append(
            f"Feature count {n} below minimum {lo}. "
            "Endpoint may be returning truncated results, or the DFIRM panel "
            "may have been revised. Check the query geometry and radius."
        )
    if n > hi:
        issues.append(
            f"Feature count {n} above maximum {hi}. "
            "Search radius may include additional DFIRM panels, or the panel "
            "was expanded. Verify spatial filter is working."
        )

    if n == 0:
        issues.append(
            "Zero features returned. Possible causes: DFIRM_ID changed, "
            "endpoint retired, geometry/radius mismatch, or spatial filter "
            "not applied."
        )
        return issues

    # Gate 3: Required fields
    props = features[0].get("properties", {})
    missing_fields = REQUIRED_FIELDS - set(props.keys())
    if missing_fields:
        issues.append(f"Missing required fields: {sorted(missing_fields)}")

    # Gate 4: Geometry type
    geom_types = set()
    for f in features:
        g = f.get("geometry")
        if g is not None:
            geom_types.add(g.get("type"))
    if geom_types != {EXPECTED_GEOMETRY_TYPE}:
        issues.append(
            f"Unexpected geometry types: {sorted(geom_types)}. "
            f"Expected: {EXPECTED_GEOMETRY_TYPE}."
        )

    # Gate 5: Total area
    total_area_m2 = sum(
        f.get("properties", {}).get("Shape__Area", 0) or 0 for f in features
    )
    total_area_km2 = total_area_m2 / 1e6
    area_lo, area_hi = EXPECTED_TOTAL_AREA_KM2_RANGE
    if not (area_lo <= total_area_km2 <= area_hi):
        issues.append(
            f"Total area {total_area_km2:.1f} km² outside expected range "
            f"[{area_lo}, {area_hi}]. Shape__Area may have changed units or "
            "the spatial filter may include unexpected panels."
        )

    # Gate 6: Recognized zone values
    zones = {f.get("properties", {}).get("FLD_ZONE", "")
             for f in features}
    unrecognized = zones - EXPECTED_ZONES - {""}
    if unrecognized:
        issues.append(
            f"Unrecognized FLD_ZONE values: {sorted(unrecognized)}. "
            "FEMA may have introduced new zone classifications. Review before "
            "accepting."
        )

    # Gate 7: DFIRM_ID consistency
    firm_ids = {f.get("properties", {}).get("DFIRM_ID", "")
                for f in features}
    if firm_ids != {TARGET_DFIRM}:
        issues.append(
            f"Unexpected DFIRM_ID values: {sorted(firm_ids)}. "
            f"Expected: {TARGET_DFIRM}. Spatial filter radius may be too large."
        )

    return issues


def _zone_summary(data: dict[str, Any]) -> dict[str, int]:
    """Return {FLD_ZONE: count} for the response features."""
    zones: dict[str, int] = {}
    for f in data.get("features", []):
        z = f.get("properties", {}).get("FLD_ZONE", "UNKNOWN")
        zones[z] = zones.get(z, 0) + 1
    return zones


# ---------------------------------------------------------------------------
# Diff against canonical
# ---------------------------------------------------------------------------

def _strip_metadata(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy without the metadata wrapper (if present).
    The metadata key is added by this script on write and contains
    timestamps that prevent byte-identical comparison."""
    if "metadata" in data:
        data = {k: v for k, v in data.items() if k != "metadata"}
    return data


def _diff_against_canonical(live: dict[str, Any]) -> dict[str, Any]:
    """Compare live response against the committed canonical file.

    Returns a dict with keys:
      exists: bool — canonical file exists
      feature_count_match: bool | None
      field_match: bool | None
      zone_match: bool | None
      byte_identical: bool | None
      canonical_path: str
      issues: list[str] — human-readable differences
    """
    result: dict[str, Any] = {
        "exists": OUTPUT.exists(),
        "feature_count_match": None,
        "field_match": None,
        "zone_match": None,
        "byte_identical": None,
        "canonical_path": str(OUTPUT),
        "issues": [],
    }

    if not OUTPUT.exists():
        result["issues"].append("No canonical file exists — first fetch.")
        return result

    with open(OUTPUT) as f:
        canonical = json.load(f)

    live_features = live.get("features", [])
    canon_features = canonical.get("features", [])

    # Feature count
    result["feature_count_match"] = len(live_features) == len(canon_features)
    if not result["feature_count_match"]:
        result["issues"].append(
            f"Feature count differs: live={len(live_features)}, "
            f"canonical={len(canon_features)}"
        )

    # Field names
    if live_features and canon_features:
        live_keys = set(live_features[0]["properties"].keys())
        canon_keys = set(canon_features[0]["properties"].keys())
        result["field_match"] = live_keys == canon_keys
        if not result["field_match"]:
            added = sorted(live_keys - canon_keys)
            removed = sorted(canon_keys - live_keys)
            if added:
                result["issues"].append(f"New fields: {added}")
            if removed:
                result["issues"].append(f"Removed fields: {removed}")

    # Zone distribution
    live_zones = _zone_summary(live)
    canon_zones = _zone_summary(canonical)
    result["zone_match"] = live_zones == canon_zones
    if not result["zone_match"]:
        result["issues"].append(
            f"Zone distribution differs:\n  live: {live_zones}\n  canon: {canon_zones}"
        )

    # Byte-identical (quick check: same JSON serialization, metadata stripped)
    live_stripped = _strip_metadata(live)
    canon_stripped = _strip_metadata(canonical)
    live_bytes = json.dumps(live_stripped, sort_keys=True, separators=(",", ":"))
    canon_bytes = json.dumps(canon_stripped, sort_keys=True, separators=(",", ":"))
    result["byte_identical"] = live_bytes == canon_bytes

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch FEMA NFHL flood hazard zones for the study area."
    )
    parser.add_argument(
        "--write", action="store_true",
        help="Write fetched data to the canonical output file (default: dry-run)."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Write even when validation gates issue warnings (use with caution)."
    )
    parser.add_argument(
        "--parcel", type=Path, default=PARCEL,
        help="Path to parcel boundary GeoJSON (default from config)."
    )
    parser.add_argument(
        "--output", type=Path, default=OUTPUT,
        help="Output path for FEMA GeoJSON."
    )
    parser.add_argument(
        "--radius", type=int, default=SEARCH_RADIUS_M,
        help=f"Search radius in meters (default: {SEARCH_RADIUS_M})."
    )
    parser.add_argument(
        "--dfirm", type=str, default=TARGET_DFIRM,
        help=f"DFIRM panel ID (default: {TARGET_DFIRM})."
    )
    args = parser.parse_args(argv)

    # Resolve parcel path relative to project root if relative
    parcel_path = args.parcel
    if not parcel_path.is_absolute():
        parcel_path = PROJECT / parcel_path
    if not parcel_path.exists():
        print(f"ERROR: Parcel file not found: {parcel_path}", file=sys.stderr)
        return 1

    output_path = args.output
    if not output_path.is_absolute():
        output_path = PROJECT / output_path

    # --- Fetch ---
    print(f"Parcel: {parcel_path}")
    print(f"DFIRM: {args.dfirm}, radius: {args.radius}m")

    try:
        lon, lat = _parcel_center(parcel_path)
    except Exception as e:
        print(f"ERROR: Could not read parcel center: {e}", file=sys.stderr)
        return 1

    print(f"Center: {lon:.6f}, {lat:.6f}")
    print("Querying ArcGIS REST ...")

    try:
        data = _query_dfirm(lon, lat)
    except RuntimeError as e:
        print(f"FETCH FAILED: {e}", file=sys.stderr)
        return 1

    n = len(data.get("features", []))
    print(f"Received: {n} features, {len(json.dumps(data)):,} bytes")

    # --- Validate ---
    issues = _validate_response(data, lon, lat)
    has_errors = any(
        "error" in i.lower() or "missing" in i.lower() or "zero" in i.lower()
        for i in issues
    )

    if issues:
        severity = "ERROR" if has_errors else "WARNING"
        for msg in issues:
            print(f"  [{severity}] {msg}")

    if has_errors:
        print("\nValidation errors detected. Aborting. Review the issues above.")
        print("If the endpoint shape has changed legitimately, update the")
        print("EXPECTED_* constants at the top of this script and re-run.")
        return 1

    # --- Diff ---
    diff = _diff_against_canonical(data)
    if diff["issues"]:
        print("\n--- Diff vs canonical ---")
        for msg in diff["issues"]:
            print(f"  {msg}")

    if diff.get("byte_identical"):
        print("\n✓ Live response is byte-identical to canonical file.")
        print("  No update needed.")
        return 0

    # --- Write ---
    zone_summary = _zone_summary(data)
    print(f"\nZone distribution: {zone_summary}")

    if not args.write:
        print("\nDry run — not writing. Pass --write to update canonical file.")
        if not diff.get("byte_identical") and diff.get("exists"):
            print("Differences detected. Decide whether canonical file is stale")
            print("or the endpoint changed shape before writing.")
        return 0

    # Add metadata
    data.setdefault("metadata", {})
    data["metadata"]["fetched_utc"] = datetime.now(timezone.utc).isoformat()
    data["metadata"]["source"] = ENDPOINT
    data["metadata"]["query_lon"] = lon
    data["metadata"]["query_lat"] = lat
    data["metadata"]["query_radius_m"] = args.radius
    data["metadata"]["dfirm_id"] = args.dfirm

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f)
    print(f"Written: {output_path} ({n} features)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
