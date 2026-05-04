from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import earthaccess
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from shapely.geometry import mapping

from scripts.init_env import load_env
from scripts.study_config import config_path, step_path
from scripts.study_utils import read_vector

LOCAL_AOI_PATH = config_path("paths", "local_aoi")
PARCEL_BOUNDARY_PATH = config_path("paths", "parcel_boundary")
FEMA_PATH = config_path("paths", "hazard_polygons")
STREAMS_PATH = config_path("paths", "selected_streams")
OUTDIR = step_path("satellite_validation", "outdir")
DOWNLOAD_DIR = step_path("satellite_validation", "download_dir")
SUMMARY_CSV = step_path("satellite_validation", "summary_csv")
SUMMARY_JSON = step_path("satellite_validation", "summary_json")
SELECTED_JSON = step_path("satellite_validation", "selected_json")

SEARCHES = [
    {
        "label": "OPERA DSWx-HLS 2023-2024 all seasons",
        "short_name": "OPERA_L3_DSWX-HLS_V1",
        "temporal": ("2023-01-01", "2024-12-31"),
        "max_items": 400,
    },
    {
        "label": "OPERA DSWx-S1 2024 viable coverage",
        "short_name": "OPERA_L3_DSWX-S1_V1",
        "temporal": ("2024-08-25", "2024-12-31"),
        "max_items": 100,
    },
]

WATER_CLASSES = {1, 2}


@dataclass
class CandidateStats:
    collection: str
    short_name: str
    native_id: str
    concept_id: str
    date: str
    data_url: str
    browse_url: str | None
    local_path: str
    browse_path: str | None
    raster_crs: str
    raster_shape: str
    valid_pixels: int
    water_pixels: int
    local_valid_pixels: int
    local_water_pixels: int
    parcel_valid_pixels: int
    parcel_water_pixels: int
    local_water_share: float
    parcel_water_share: float
    overall_water_share: float
    bbox_geojson: dict | None = None


def geometry_from_item(item: dict) -> dict:
    rects = item["umm"]["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["BoundingRectangles"]
    rect = rects[0]
    return {
        "type": "Polygon",
        "coordinates": [[
            [rect["WestBoundingCoordinate"], rect["SouthBoundingCoordinate"]],
            [rect["EastBoundingCoordinate"], rect["SouthBoundingCoordinate"]],
            [rect["EastBoundingCoordinate"], rect["NorthBoundingCoordinate"]],
            [rect["WestBoundingCoordinate"], rect["NorthBoundingCoordinate"]],
            [rect["WestBoundingCoordinate"], rect["SouthBoundingCoordinate"]],
        ]],
    }


def related_url(item: dict, kind: str, suffix: str) -> str | None:
    for ru in item["umm"].get("RelatedUrls", []):
        if ru.get("Type") == kind and ru.get("URL", "").endswith(suffix):
            return ru["URL"]
    return None


def download_url(url: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    downloaded = earthaccess.download(url, local_path=dest_dir, show_progress=False)
    return Path(downloaded[0])


def read_stats(
    raster_path: Path,
    local_aoi: gpd.GeoDataFrame,
    parcel: gpd.GeoDataFrame,
) -> dict:
    with rasterio.open(raster_path) as src:
        arr = src.read(1)
        local_r = local_aoi.to_crs(src.crs)
        parcel_r = parcel.to_crs(src.crs)
        local_mask = geometry_mask(
            [mapping(g) for g in local_r.geometry],
            out_shape=arr.shape,
            transform=src.transform,
            invert=True,
        )
        parcel_mask = geometry_mask(
            [mapping(g) for g in parcel_r.geometry],
            out_shape=arr.shape,
            transform=src.transform,
            invert=True,
        )
        valid = np.ones(arr.shape, dtype=bool) if src.nodata is None else arr != src.nodata
        water = np.isin(arr, list(WATER_CLASSES))

        local_valid = int((valid & local_mask).sum())
        parcel_valid = int((valid & parcel_mask).sum())
        local_water = int((water & valid & local_mask).sum())
        parcel_water = int((water & valid & parcel_mask).sum())
        overall_water = int((water & valid).sum())
        valid_pixels = int(valid.sum())

        return {
            "raster_crs": str(src.crs),
            "raster_shape": f"{src.height}x{src.width}",
            "valid_pixels": valid_pixels,
            "water_pixels": overall_water,
            "local_valid_pixels": local_valid,
            "local_water_pixels": local_water,
            "parcel_valid_pixels": parcel_valid,
            "parcel_water_pixels": parcel_water,
            "local_water_share": (local_water / local_valid) if local_valid else 0.0,
            "parcel_water_share": (parcel_water / parcel_valid) if parcel_valid else 0.0,
            "overall_water_share": (overall_water / valid_pixels) if valid_pixels else 0.0,
        }


def collect_candidates(
    local_aoi: gpd.GeoDataFrame,
    parcel: gpd.GeoDataFrame,
) -> list[CandidateStats]:
    minx, miny, maxx, maxy = local_aoi.total_bounds
    bbox = (minx, miny, maxx, maxy)
    rows: list[CandidateStats] = []
    for search in SEARCHES:
        items = earthaccess.search_data(
            short_name=search["short_name"],
            bounding_box=bbox,
            temporal=search["temporal"],
            count=search["max_items"],
        )
        for item in items:
            native_id = item["meta"]["native-id"]
            concept_id = item["meta"]["concept-id"]
            date = item["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:10]
            data_url = related_url(item, "GET DATA", "_B01_WTR.tif")
            browse_url = related_url(item, "GET RELATED VISUALIZATION", "_BROWSE.png")
            if not data_url:
                continue
            local_path = download_url(data_url, DOWNLOAD_DIR)
            browse_path = None
            if browse_url:
                try:
                    browse_path = str(download_url(browse_url, DOWNLOAD_DIR))
                except Exception:
                    browse_path = None

            bbox_geojson = geometry_from_item(item)
            stats = read_stats(local_path, local_aoi, parcel)
            rows.append(CandidateStats(
                collection=search["label"],
                short_name=search["short_name"],
                native_id=native_id,
                concept_id=concept_id,
                date=date,
                data_url=data_url,
                browse_url=browse_url,
                local_path=str(local_path),
                browse_path=browse_path,
                raster_crs=stats["raster_crs"],
                raster_shape=stats["raster_shape"],
                valid_pixels=stats["valid_pixels"],
                water_pixels=stats["water_pixels"],
                local_valid_pixels=stats["local_valid_pixels"],
                local_water_pixels=stats["local_water_pixels"],
                parcel_valid_pixels=stats["parcel_valid_pixels"],
                parcel_water_pixels=stats["parcel_water_pixels"],
                local_water_share=stats["local_water_share"],
                parcel_water_share=stats["parcel_water_share"],
                overall_water_share=stats["overall_water_share"],
                bbox_geojson=bbox_geojson,
            ))
    return rows


def choose_selected(candidates: list[CandidateStats]) -> list[CandidateStats]:
    selected: list[CandidateStats] = []
    for collection in sorted({c.collection for c in candidates}):
        group = [c for c in candidates if c.collection == collection]
        group.sort(
            key=lambda c: (c.local_water_pixels, c.parcel_water_pixels, c.water_pixels, c.overall_water_share),
            reverse=True,
        )
        selected.append(group[0])
    return selected


def save_summaries(candidates: list[CandidateStats], selected: list[CandidateStats]) -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    # Exclude bbox_geojson from serialized output (it's a geometry, not a metric)
    def _to_dict_no_bbox(c: CandidateStats) -> dict:
        d = asdict(c)
        d.pop("bbox_geojson", None)
        return d

    df = pd.DataFrame([_to_dict_no_bbox(c) for c in candidates])
    df.sort_values(
        ["collection", "local_water_pixels", "parcel_water_pixels", "water_pixels"],
        ascending=[True, False, False, False],
        inplace=True,
    )
    df.to_csv(SUMMARY_CSV, index=False)
    SUMMARY_JSON.write_text(json.dumps([_to_dict_no_bbox(c) for c in candidates], indent=2), encoding="utf-8")
    SELECTED_JSON.write_text(json.dumps([asdict(s) for s in selected], indent=2), encoding="utf-8")


def main() -> None:
    load_env()
    earthaccess.login(strategy="environment")

    # Read vectors once; pass GeoDataFrames to downstream functions.
    local_aoi = read_vector(LOCAL_AOI_PATH, crs="EPSG:4326")
    parcel = read_vector(PARCEL_BOUNDARY_PATH, crs="EPSG:4326")

    candidates = collect_candidates(local_aoi, parcel)
    selected = choose_selected(candidates)
    save_summaries(candidates, selected)

    print(SUMMARY_CSV)
    print(SELECTED_JSON)


if __name__ == "__main__":
    main()
