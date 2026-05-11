"""Bootstrap: compute parcel contributing area from a 10m DEM.

Run once on a fresh clone to produce the contributing area polygon
required by deliverable/_pipeline.py. All intermediate files are
written to data/derived/bootstrap/ (gitignored) and cleaned up on
success. Only the contributing area GeoJSONs persist.

Usage:
    .venv/bin/python scripts/bootstrap.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deliverable import fetch_dem, preprocess_dem, compute_dinf
from deliverable.upstream import contributing_area

PARCEL     = ROOT / "data/raw/sangis/deanza_villas_complex_boundary.geojson"
BOOTSTRAP  = ROOT / "data/derived/bootstrap"
VECTORS    = ROOT / "data/derived/vectors"
MAPS       = ROOT / "outputs/maps"

BOOTSTRAP_RES_M    = 10.0
BOOTSTRAP_BUFFER_M = 25_000.0


def main() -> None:
    BOOTSTRAP.mkdir(parents=True, exist_ok=True)
    VECTORS.mkdir(parents=True, exist_ok=True)

    parcel = gpd.read_file(PARCEL)

    print("=== Step 1: fetch 10m DEM ===")
    dem_raw = fetch_dem(
        parcel,
        resolution=BOOTSTRAP_RES_M,
        buffer_m=BOOTSTRAP_BUFFER_M,
        output=BOOTSTRAP / "dem_10m.tif",
    )

    print("\n=== Step 2: preprocess ===")
    dem_filled = preprocess_dem(
        dem_raw,
        output=BOOTSTRAP / "dem_10m_filled.tif",
        strategy="breach_then_fill",
    )

    print("\n=== Step 3: D∞ pointer ===")
    compute_dinf(
        dem_filled,
        output=BOOTSTRAP / "dinf_accum_10m.tif",
        pointer=BOOTSTRAP / "dinf_pointer_10m.tif",
    )

    print("\n=== Step 4: upstream BFS ===")
    parcel_seeded = parcel.copy()
    parcel_seeded.geometry = parcel.geometry.buffer(3.0)

    gdf_4326 = contributing_area(
        BOOTSTRAP / "dinf_pointer_10m.tif",
        parcel_seeded,
        output_mask=BOOTSTRAP / "contributing_area_mask.tif",
    )

    print("\n=== Step 5: save contributing area ===")
    # Buffer by the bootstrap resolution to absorb 10m cell quantization
    # at the polygon boundary before using it as the 1m DEM clip extent.
    gdf_5070 = gdf_4326.to_crs("EPSG:5070")
    gdf_5070.geometry = gdf_5070.geometry.buffer(BOOTSTRAP_RES_M)
    gdf_4326_padded = gdf_5070.to_crs("EPSG:4326")

    out_5070 = VECTORS / "deanza_parcel_contributing_area_5070.geojson"
    out_wgs84 = VECTORS / "deanza_parcel_contributing_area.geojson"
    gdf_5070.to_file(out_5070, driver="GeoJSON")
    gdf_4326_padded.to_file(out_wgs84, driver="GeoJSON")
    shutil.copy(out_wgs84, MAPS / "deanza_parcel_contributing_area.geojson")
    print(f"  {out_5070}")
    print(f"  {out_wgs84}")
    print(f"  {MAPS / 'deanza_parcel_contributing_area.geojson'}")

    print("\n=== Step 6: cleanup ===")
    shutil.rmtree(BOOTSTRAP)
    print("  Bootstrap intermediates removed.")

    area_km2 = gdf_5070.iloc[0].get("area_km2", "?")
    print(f"\nDone. Contributing area: {area_km2} km²")
    print(f"Next: .venv/bin/python -m deliverable._pipeline all")


if __name__ == "__main__":
    main()
