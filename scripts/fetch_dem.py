from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import py3dep

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AOI = ROOT / "data/vectors/borrego_valley_context_8km_aoi.geojson"
DEFAULT_OUT = ROOT / "data/raw/dem/borrego_valley_3dep_10m.tif"


def fetch_dem(aoi_path: Path, output_path: Path, resolution: int = 10) -> Path:
    aoi = gpd.read_file(aoi_path).to_crs(4326)
    xmin, ymin, xmax, ymax = aoi.total_bounds
    dem = py3dep.get_dem((xmin, ymin, xmax, ymax), resolution=resolution, crs=4326)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dem.rio.to_raster(output_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a prototype DEM for the Borrego Valley context AOI.")
    parser.add_argument("--aoi", type=Path, default=DEFAULT_AOI)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--resolution", type=int, default=10, help="3DEP target resolution in meters")
    args = parser.parse_args()

    out = fetch_dem(args.aoi, args.out, args.resolution)
    print(out)


if __name__ == "__main__":
    main()
