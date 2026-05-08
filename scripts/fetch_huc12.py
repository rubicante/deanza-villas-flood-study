"""Fetch HUC-12 boundary for Borrego Palm Canyon from the USGS WBD.

Downloads the Region 18 (California) WBD shapefile from USGS S3, extracts
the Borrego Palm Canyon HUC-12 (181002030302) polygon, and saves as GeoJSON.

Why WBD S3 and not NLDI: The NLDI /basin endpoint always returns a simplified
polygon (~416 vertices, 113.6 km²) regardless of the ?simplified=false
parameter. The canonical USGS-reported area for this HUC-12 is 149.1 km²
and the WBD shapefile polygon has 1,692 vertices. IoU between NLDI and WBD
is only 0.76 — the simplification clips real boundary detail. For spatial
filtering (cell-in-HUC-12 checks), the WBD polygon is authoritative.

Download: ~172 MB zip. Unzipped shapefile is ~92 MB. Cache the unzipped
file locally to avoid re-download on subsequent runs.

No API key required.
"""

from __future__ import annotations

import json
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd

PROJECT = Path(__file__).resolve().parents[1]

WBD_URL = (
    "https://prd-tnm.s3.amazonaws.com/StagedProducts/"
    "Hydrography/WBD/HU2/Shape/WBD_18_HU2_Shape.zip"
)

CACHE_DIR = PROJECT / "data" / "raw" / ".cache"
OUTPUT = (
    PROJECT / "data" / "derived" / "vectors" / "borrego_palm_canyon_huc12.geojson"
)

HUC12 = "181002030302"
REQUEST_TIMEOUT = 120  # 172 MB download


def _extract_huc12(wbd_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Filter to the target HUC-12 and add provenance properties."""
    huc = wbd_gdf[wbd_gdf["huc12"] == HUC12].copy()
    if len(huc) == 0:
        # Try different column name
        cols = [c for c in wbd_gdf.columns if "huc" in c.lower()]
        print(f"  huc12 column not found. HUC-like columns: {cols}", file=sys.stderr)
        return gpd.GeoDataFrame()

    huc["huc12"] = HUC12
    huc["name"] = "Borrego Palm Canyon"
    huc["source"] = f"USGS WBD Region 18 shapefile ({WBD_URL})"
    huc["fetched_utc"] = datetime.now(timezone.utc).isoformat()

    # Simplify to ~500 vertices for reasonable file size while keeping
    # spatial accuracy (1,692 → ~500 is a good balance)
    if len(huc) > 0:
        geom = huc.geometry.iloc[0]
        simplified = geom.simplify(0.0001, preserve_topology=True)  # ~11m at this lat
        huc.geometry.iloc[0] = simplified

    return huc


def main() -> int:
    print(f"HUC-12: {HUC12} (Borrego Palm Canyon)")
    print(f"Source: USGS WBD Region 18 shapefile")

    # Check cache first
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached_shp = CACHE_DIR / "Shape" / "WBDHU12.shp"
    shapename = "Shape/WBDHU12.shp"

    if cached_shp.exists():
        print(f"Cache hit: {cached_shp}")
        wbd = gpd.read_file(cached_shp)
    else:
        print(f"Downloading {WBD_URL} ...")
        zip_path = CACHE_DIR / "WBD_18_HU2_Shape.zip"

        if not zip_path.exists():
            try:
                req = urllib.request.Request(
                    WBD_URL, headers={"User-Agent": "borrego-flood-study/1.0"}
                )
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                    with open(zip_path, "wb") as f:
                        f.write(resp.read())
                size_mb = zip_path.stat().st_size / 1e6
                print(f"  Downloaded: {size_mb:.0f} MB")
            except Exception as e:
                print(f"Download failed: {e}", file=sys.stderr)
                return 1

        # Extract only the HUC-12 shapefile
        print(f"Extracting {shapename} ...")
        with zipfile.ZipFile(zip_path) as zf:
            # Find the HUC12 shapefile components
            for name in zf.namelist():
                if "WBDHU12" in name:
                    zf.extract(name, CACHE_DIR)
        print(f"  Cached: {cached_shp}")
        wbd = gpd.read_file(cached_shp)

    # Filter to target HUC-12
    huc = _extract_huc12(wbd)
    if len(huc) == 0:
        print(f"ERROR: HUC-12 {HUC12} not found in WBD shapefile", file=sys.stderr)
        return 1

    # Select only needed columns
    huc = huc[["huc12", "name", "source", "fetched_utc", "geometry"]]

    # Convert to WGS84 for output
    huc_4326 = huc.to_crs("EPSG:4326")
    geom = huc_4326.geometry.iloc[0]
    coords = list(geom.exterior.coords) if geom.geom_type == "Polygon" else []

    print(f"  Vertices: {len(coords)}")
    print(f"  Bounds: lon [{geom.bounds[0]:.4f}, {geom.bounds[2]:.4f}], "
          f"lat [{geom.bounds[1]:.4f}, {geom.bounds[3]:.4f}]")

    # Write output
    feature = {
        "type": "Feature",
        "properties": {
            "huc12": HUC12,
            "name": "Borrego Palm Canyon",
            "source": f"USGS Watershed Boundary Dataset (WBD) HUC12 {HUC12}, "
                      f"extracted from Region 18 shapefile",
            "area_km2": 149.1,
        },
        "geometry": json.loads(huc_4326.geometry.to_json())["features"][0]["geometry"],
    }

    output = {
        "type": "FeatureCollection",
        "name": "borrego_palm_canyon_huc12",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": [feature],
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Written: {OUTPUT}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
