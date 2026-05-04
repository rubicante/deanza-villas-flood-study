from __future__ import annotations

import geopandas as gpd
import py3dep

from scripts.study_config import config_path

AOI_PATH = config_path("paths", "dem_source_aoi")
OUTPUT_PATH = config_path("paths", "dem_source_output")
RESOLUTION = 10


def fetch_dem() -> None:
    aoi = gpd.read_file(AOI_PATH).to_crs(4326)
    xmin, ymin, xmax, ymax = aoi.total_bounds
    dem = py3dep.get_dem((xmin, ymin, xmax, ymax), resolution=RESOLUTION, crs=4326)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    dem.rio.to_raster(OUTPUT_PATH)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    fetch_dem()
