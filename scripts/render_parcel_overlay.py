from __future__ import annotations

import geopandas as gpd

from scripts.study_config import config_path, deliverable_path, step_path
from scripts.study_utils import build_standard_map, ensure_crs

STREAMS_PATH = config_path("paths", "selected_streams")
PARCEL_BOUNDARY_PATH = config_path("paths", "parcel_boundary")
PARCEL_POLYGONS_PATH = config_path("paths", "parcel_polygons")
HAZARD_PATH = config_path("paths", "hazard_polygons")
LOCAL_AOI_PATH = config_path("paths", "local_aoi")
CONTEXT_AOI_PATH = config_path("paths", "context_aoi")
OUTDIR = step_path("parcel_overlay", "outdir")
MAP_PATH = deliverable_path("parcel_overlay_map")


def main() -> None:
    # Load vectors
    parcel_boundary = ensure_crs(gpd.read_file(PARCEL_BOUNDARY_PATH))
    parcel_polygons = ensure_crs(gpd.read_file(PARCEL_POLYGONS_PATH))
    hazard = ensure_crs(gpd.read_file(HAZARD_PATH))
    local_aoi = ensure_crs(gpd.read_file(LOCAL_AOI_PATH))
    context_aoi = ensure_crs(gpd.read_file(CONTEXT_AOI_PATH))

    # Use clipped parcel streams if available, otherwise full network
    clipped_gpkg = OUTDIR / "deanza_villas_2km_1m_dem_filled_streams_5000_in_parcel.gpkg"
    map_streams_path = clipped_gpkg if clipped_gpkg.exists() else STREAMS_PATH
    streams = ensure_crs(gpd.read_file(map_streams_path))

    m = build_standard_map(
        center_gdf=parcel_boundary,
        zoom=16,
        satellite_basemap=True,
        hazard=hazard,
        context_aoi=context_aoi,
        local_aoi=local_aoi,
        parcel_polygons=parcel_polygons,
        parcel_boundary=parcel_boundary,
        streams=streams,
    )
    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(MAP_PATH))
    print(MAP_PATH)


if __name__ == "__main__":
    main()
