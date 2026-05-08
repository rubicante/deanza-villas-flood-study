"""Recreate the De Anza Villas parcel boundary from SanGIS source data.

Reads the individual SanGIS parcel polygons, filters out Vista Villas
(APN prefix 14026410 — a separate community), and merges the remaining
two De Anza blocks across Monroe St with a straight-bridge connection.

The bridge uses a convex-hull-of-the-gap approach:
1. Buffer(15m) the union of the two blocks to fill the road gap
2. Buffer(-15m) to shrink back to near-original boundaries
3. Extract the bridge-gap polygon (largest fragment of bridged - union)
4. Take its convex hull for straight top/bottom bridge edges
5. Union with the original parcel footprints

Outputs:
  data/raw/sangis/deanza_villas_parcel_polygons.geojson  — 36 De Anza parcels
  data/raw/sangis/deanza_villas_complex_boundary.geojson  — dissolved boundary
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
from shapely.geometry import mapping
from shapely.ops import unary_union

PROJECT = Path(__file__).resolve().parents[1]

# Canonical paths
PARCELS_IN = PROJECT / "data" / "raw" / "sangis" / "deanza_villas_parcel_polygons.geojson"
PARCELS_OUT = PARCELS_IN  # overwrite in place
BOUNDARY_OUT = PROJECT / "data" / "raw" / "sangis" / "deanza_villas_complex_boundary.geojson"

# Vista Villas exclusion
VISTA_APN_PREFIX = "14026410"

# Bridge parameters (meters, in EPSG:5070)
BRIDGE_BUFFER_M = 15
GAP_MIN_AREA_M2 = 10  # ignore zero-area slivers from buffer operation


def main() -> int:
    if not PARCELS_IN.exists():
        print(f"ERROR: Source parcel file not found: {PARCELS_IN}", file=sys.stderr)
        return 1

    parcels = gpd.read_file(PARCELS_IN)
    n_original = len(parcels)
    print(f"Source: {n_original} parcels from {PARCELS_IN}")

    # --- Filter out Vista Villas ---
    vista_mask = parcels.apn.str.startswith(VISTA_APN_PREFIX)
    vista_count = vista_mask.sum()
    if vista_count == 0:
        print("No Vista Villas parcels found — nothing to filter.")
    else:
        vista_apns = sorted(parcels[vista_mask].apn.tolist())
        print(f"Removing {vista_count} Vista Villas parcels: "
              f"{vista_apns[0]}...{vista_apns[-1]}")
        parcels = parcels[~vista_mask].copy()

    n_deanza = len(parcels)
    print(f"De Anza parcels: {n_deanza}")

    # --- Write filtered individual parcels ---
    parcels.to_file(PARCELS_OUT, driver="GeoJSON")
    print(f"Wrote parcel polygons: {PARCELS_OUT}")

    # --- Build dissolved boundary in EPSG:5070 for real-meter operations ---
    parcels_5070 = parcels.to_crs("EPSG:5070")
    union = parcels_5070.geometry.union_all()
    print(f"Union of {n_deanza} parcels: {union.area:.0f} m² "
          f"({union.area / 10000:.2f} ha), {union.geom_type}")

    # --- Bridge the gap between blocks ---
    # Buffer to fill road gap, then shrink back
    bridged = union.buffer(BRIDGE_BUFFER_M).buffer(-BRIDGE_BUFFER_M)
    fill_before = bridged.area - union.area
    print(f"Buffer-bridge: {bridged.area:.0f} m² (+{fill_before:.0f} m² fill)")

    # Extract the bridge gap — the area the buffer added
    gap_parts = list(bridged.difference(union).geoms)
    real_gaps = [g for g in gap_parts if g.area > GAP_MIN_AREA_M2]
    if not real_gaps:
        real_gaps = [max(gap_parts, key=lambda g: g.area)]
    bridge_gap = real_gaps[0]

    # Convex hull of the bridge gap → straight top/bottom edges
    bridge_straight = bridge_gap.convex_hull
    print(f"Bridge gap: {bridge_gap.area:.0f} m² → hull: {bridge_straight.area:.0f} m²")

    # Final: original parcels + straight bridge
    result = unary_union([union, bridge_straight])
    print(f"Result: {result.area:.0f} m² ({result.area / 10000:.2f} ha), "
          f"+{result.area - union.area:.0f} m² fill, {result.geom_type}")

    # --- Convert to WGS84 and save ---
    result_4326 = gpd.GeoDataFrame(geometry=[result], crs="EPSG:5070").to_crs("EPSG:4326")
    boundary = result_4326.geometry.iloc[0]

    feature = {
        "type": "Feature",
        "properties": {
            "name": "De Anza Villas complex boundary",
            "source": "SanGIS parcel polygons, subname LIKE 'DE ANZA VILLAS%', "
                      "excluding Vista Villas (APN 14026410xx). "
                      "Two blocks merged across Monroe St ROW with straight bridge.",
            "parcel_count": n_deanza,
            "excluded_count": int(vista_count),
            "excluded_reason": "Vista Villas — separate community (APN prefix 14026410)",
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
    print(f"Wrote dissolved boundary: {BOUNDARY_OUT}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
