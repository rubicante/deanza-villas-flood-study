"""Digitize DRI 2015 active/inactive fan map and compare roughness rasters.

This is a pragmatic, reproducible extraction from page 20 of the public DRI
presentation PDF. The page has a graticule but no downloadable GIS layer was
found, so the map colors are classified from a rendered page and georeferenced
with approximate graticule control points.
"""

from __future__ import annotations

import json
import shutil
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import geopandas as gpd
import numpy as np
import rasterio
from affine import Affine
from PIL import Image
from rasterio.features import shapes
from rasterio.mask import mask as rio_mask
from scipy import ndimage
from shapely.geometry import shape, box, mapping
from shapely.ops import unary_union

PROJECT = Path(__file__).resolve().parents[1]
PDF_URL = "https://cdn.ymaws.com/floodplain.org/resource/resmgr/2015Conference/Wednesday/Borrego-Springs-Alluvial-Fan.pdf"
PDF_PATH = PROJECT / "data/raw/dri_2015_borrego_fans.pdf"
EXISTING_PDF = PROJECT / "data/raw/docs/dri_2015_fan_mapping.pdf"
WORK_DIR = PROJECT / "data/raw/manual"
PAGE_RENDER = WORK_DIR / "dri_page_20_300dpi.png"
MASK_OVERLAY = WORK_DIR / "dri_page_20_class_masks_on_map.png"
ZONES_4326 = PROJECT / "data/derived/vectors/dri_2015_fan_zones.geojson"
ZONES_5070 = PROJECT / "data/derived/vectors/dri_2015_fan_zones_epsg5070.geojson"
STATS_JSON = PROJECT / "data/derived/2km_aoi/dri_roughness_comparison_stats.json"
ROUGHNESS_RASTERS: dict[str, Path] = {
    "roughness_magnitude_m": PROJECT / "data/derived/2km_aoi/deanza_villas_2km_1m_dem_multiscale_roughness_mag.tif",
    "roughness_scale_m": PROJECT / "data/derived/2km_aoi/deanza_villas_2km_1m_dem_multiscale_roughness_scale.tif",
}
PARCEL = PROJECT / "data/raw/sangis/deanza_villas_complex_boundary.geojson"

# Coordinates were estimated from the rendered page-20 graticule at 216 dpi
# (PyMuPDF matrix=3). They are scaled to the target render dpi below. Values are
# labeled graticule lines, not extrapolated page-frame edges.
GCP_DPI = 216.0
RENDER_DPI = 300.0
BASE_X_GCPS = [
    (775, -116 - 26 / 60),
    (944, -116 - 24 / 60),
    (1113, -116 - 22 / 60),
    (1282, -116 - 20 / 60),
    (1451, -116 - 18 / 60),
    (1620, -116 - 16 / 60),
]
BASE_Y_GCPS = [
    (457, 33 + 22 / 60),
    (664, 33 + 20 / 60),
    (871, 33 + 18 / 60),
    (1078, 33 + 16 / 60),
    (1285, 33 + 14 / 60),
    (1492, 33 + 12 / 60),
]
# Map-frame and legend masks estimated at 216 dpi; scale with render DPI.
BASE_MAP_FRAME = (723, 280, 1660, 1557)  # left, top, right, bottom
BASE_INSET_LEGEND = (1420, 300, 1660, 620)


@dataclass
class RasterStats:
    count: int
    mean: float | None
    std: float | None
    min: float | None
    p10: float | None
    p50: float | None
    p90: float | None
    max: float | None


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT))
    except ValueError:
        return str(path)


def ensure_pdf() -> None:
    PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    if PDF_PATH.exists() and PDF_PATH.stat().st_size > 1_000_000:
        return
    if EXISTING_PDF.exists() and EXISTING_PDF.stat().st_size > 1_000_000:
        shutil.copy2(EXISTING_PDF, PDF_PATH)
        return
    urllib.request.urlretrieve(PDF_URL, PDF_PATH)


def scaled_box(vals: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    scale = RENDER_DPI / GCP_DPI
    return tuple(int(round(v * scale)) for v in vals)  # type: ignore[return-value]


def render_page_20() -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(PDF_PATH)
    page = doc[19]  # one-based page 20
    zoom = RENDER_DPI / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    pix.save(PAGE_RENDER)


def linear_fit(gcps: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Return slope, intercept, max absolute residual for coord = slope*px+intercept."""
    scale = RENDER_DPI / GCP_DPI
    px = np.array([p * scale for p, _ in gcps], dtype=float)
    coord = np.array([c for _, c in gcps], dtype=float)
    slope, intercept = np.polyfit(px, coord, 1)
    resid = coord - (slope * px + intercept)
    return float(slope), float(intercept), float(np.abs(resid).max())


def remove_small(mask: np.ndarray, min_pixels: int) -> np.ndarray:
    labels, n = ndimage.label(mask)
    if n == 0:
        return mask
    sizes = np.bincount(labels.ravel())
    keep = sizes >= min_pixels
    keep[0] = False
    return keep[labels]


def classify_masks() -> tuple[np.ndarray, np.ndarray, Affine, dict[str, Any]]:
    img = Image.open(PAGE_RENDER).convert("RGB")
    arr = np.asarray(img)
    r = arr[..., 0].astype(int)
    g = arr[..., 1].astype(int)
    b = arr[..., 2].astype(int)

    left, top, right, bottom = scaled_box(BASE_MAP_FRAME)
    leg_left, leg_top, leg_right, leg_bottom = scaled_box(BASE_INSET_LEGEND)
    map_mask = np.zeros(r.shape, dtype=bool)
    map_mask[top:bottom, left:right] = True
    legend_mask = np.zeros(r.shape, dtype=bool)
    legend_mask[leg_top:leg_bottom, leg_left:leg_right] = True
    base = map_mask & ~legend_mask

    # Semi-transparent DRI fills over hillshade. These thresholds were tuned to
    # capture the dominant pink active fan fill and the muted olive/green inactive
    # fill while rejecting blue drainage and gray hillshade/labels.
    active = (
        base
        & (r > 150)
        & (r > g + 20)
        & (r > b + 15)
        & (g > 90)
        & (b > 90)
        & (g < 230)
        & (b < 230)
    )
    inactive = (
        base
        & (g > 90)
        & (r >= 50)
        & (b < 120)
        & (g > r + 10)
        & ((g - b) > 40)
        & (r < 180)
    )

    # Smooth single-pixel cartographic noise without swallowing small inactive patches.
    active = ndimage.binary_closing(active, structure=np.ones((3, 3), dtype=bool))
    inactive = ndimage.binary_closing(inactive, structure=np.ones((3, 3), dtype=bool))
    active = remove_small(active, min_pixels=1200)
    inactive = remove_small(inactive, min_pixels=120)

    # Inactive wins where anti-aliased classes overlap.
    active &= ~inactive

    # Save visual QC overlay.
    overlay = np.zeros((*r.shape, 4), dtype=np.uint8)
    overlay[active] = [255, 0, 0, 145]
    overlay[inactive] = [0, 220, 0, 170]
    Image.alpha_composite(Image.fromarray(arr).convert("RGBA"), Image.fromarray(overlay)).save(MASK_OVERLAY)

    lon_slope, lon_int, lon_resid = linear_fit(BASE_X_GCPS)
    lat_slope, lat_int, lat_resid = linear_fit(BASE_Y_GCPS)
    transform = Affine(lon_slope, 0.0, lon_int, 0.0, lat_slope, lat_int)
    meta = {
        "render_dpi": RENDER_DPI,
        "image_size_px": [int(arr.shape[1]), int(arr.shape[0])],
        "map_frame_px": [left, top, right, bottom],
        "masked_inset_legend_px": [leg_left, leg_top, leg_right, leg_bottom],
        "lon_fit_deg_per_px": lon_slope,
        "lat_fit_deg_per_px": lat_slope,
        "max_abs_lon_fit_residual_deg": lon_resid,
        "max_abs_lat_fit_residual_deg": lat_resid,
        "active_pixels": int(active.sum()),
        "inactive_pixels": int(inactive.sum()),
    }
    return active.astype("uint8"), inactive.astype("uint8"), transform, meta


def polygonize_zones(active: np.ndarray, inactive: np.ndarray, transform: Affine) -> gpd.GeoDataFrame:
    records: list[dict[str, Any]] = []
    for cls, mask_arr in [("active", active), ("inactive", inactive)]:
        geoms = [shape(geom) for geom, val in shapes(mask_arr, mask=mask_arr.astype(bool), transform=transform) if val == 1]
        geoms = [g for g in geoms if not g.is_empty]
        if not geoms:
            continue
        dissolved = unary_union(geoms)
        records.append(
            {
                "fan_class": cls,
                "confidence": "moderate for broad extents; low-moderate for small polygons",
                "source": "DRI 2015 presentation page 20 color-classified/georeferenced from PDF graticule",
                "geometry": dissolved,
            }
        )
    gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
    ZONES_4326.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(ZONES_4326, driver="GeoJSON")
    gdf5070 = gdf.to_crs("EPSG:5070")
    gdf5070.to_file(ZONES_5070, driver="GeoJSON")
    return gdf


def stats_for_values(vals: np.ndarray) -> RasterStats:
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return RasterStats(0, None, None, None, None, None, None, None)
    return RasterStats(
        count=int(vals.size),
        mean=float(np.mean(vals)),
        std=float(np.std(vals)),
        min=float(np.min(vals)),
        p10=float(np.percentile(vals, 10)),
        p50=float(np.percentile(vals, 50)),
        p90=float(np.percentile(vals, 90)),
        max=float(np.max(vals)),
    )


def raster_stats(path: Path, geom_gdf: gpd.GeoDataFrame) -> RasterStats:
    with rasterio.open(path) as src:
        gdf = geom_gdf.to_crs(src.crs)
        raster_bounds = gpd.GeoDataFrame(geometry=[box(*src.bounds)], crs=src.crs)
        if not bool(gdf.intersects(raster_bounds.geometry.iloc[0]).any()):
            return RasterStats(0, None, None, None, None, None, None, None)
        try:
            out, _ = rio_mask(src, [mapping(geom) for geom in gdf.geometry if not geom.is_empty], crop=True, filled=False)
        except ValueError:
            return RasterStats(0, None, None, None, None, None, None, None)
        data = out[0].astype("float64")
        # Use the mask returned by rasterio.mask so pixels outside the geometry do not
        # bias the statistics when a raster has no explicit nodata value.
        data = data.compressed() if hasattr(data, "compressed") else data[np.isfinite(data)]
        return stats_for_values(np.asarray(data, dtype="float64"))


def area_overlap_stats(zones: gpd.GeoDataFrame, parcel: gpd.GeoDataFrame, raster_crs: Any) -> dict[str, Any]:
    z = zones.to_crs(raster_crs)
    p = parcel.to_crs(raster_crs)
    parcel_union = p.geometry.union_all()
    total = float(parcel_union.area)
    out: dict[str, Any] = {"parcel_area_m2": total, "fan_class_area_m2": {}, "fan_class_area_fraction": {}}
    for _, row in z.iterrows():
        inter = row.geometry.intersection(parcel_union)
        area = float(inter.area) if not inter.is_empty else 0.0
        out["fan_class_area_m2"][row.fan_class] = area
        out["fan_class_area_fraction"][row.fan_class] = area / total if total else None
    return out


def compute_stats(zones: gpd.GeoDataFrame) -> dict[str, Any]:
    parcel = gpd.read_file(PARCEL)
    results: dict[str, Any] = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "pdf": rel(PDF_PATH),
            "rendered_page_20": rel(PAGE_RENDER),
            "classification_qc_overlay": rel(MASK_OVERLAY),
            "zones_epsg4326": rel(ZONES_4326),
            "zones_epsg5070": rel(ZONES_5070),
            "parcel": rel(PARCEL),
            "roughness_rasters": {k: rel(v) for k, v in ROUGHNESS_RASTERS.items()},
        },
        "digitization_confidence": "moderate for broad active/inactive extents; low-moderate for small inactive polygons and map-edge details",
        "roughness_stats": {},
        "parcel_zone_overlap": {},
    }
    first_raster_crs = None
    for name, path in ROUGHNESS_RASTERS.items():
        with rasterio.open(path) as src:
            first_raster_crs = src.crs
        raster_result: dict[str, Any] = {}
        for fan_class in ["active", "inactive"]:
            subset = zones[zones["fan_class"] == fan_class]
            raster_result[fan_class] = asdict(raster_stats(path, subset)) if len(subset) else asdict(RasterStats(0, None, None, None, None, None, None, None))
        raster_result["parcel"] = asdict(raster_stats(path, parcel))
        results["roughness_stats"][name] = raster_result
    if first_raster_crs is not None:
        results["parcel_zone_overlap"] = area_overlap_stats(zones, parcel, first_raster_crs)
    return results


def write_summary(stats: dict[str, Any], georef: dict[str, Any]) -> None:
    mag = stats["roughness_stats"]["roughness_magnitude_m"]
    scale = stats["roughness_stats"]["roughness_scale_m"]
    overlap = stats["parcel_zone_overlap"]

    def fmt(v: Any, nd: int = 3) -> str:
        if v is None:
            return "n/a"
        if isinstance(v, int):
            return f"{v:,}"
        if isinstance(v, float):
            return f"{v:.{nd}f}"
        return str(v)

    lines = [
        "# DRI 2015 fan-zone roughness comparison",
        "",
        "## What was produced",
        f"- Source PDF: `{rel(PDF_PATH)}`",
        f"- Rendered page 20: `{rel(PAGE_RENDER)}`",
        f"- QC overlay: `{rel(MASK_OVERLAY)}`",
        f"- Digitized fan zones, EPSG:4326: `{rel(ZONES_4326)}`",
        f"- Reprojected fan zones, EPSG:5070: `{rel(ZONES_5070)}`",
        f"- Machine-readable stats: `{rel(STATS_JSON)}`",
        "",
        "## Method summary",
        "Page 20 of the DRI 2015 presentation was rendered at 300 dpi. The visible latitude/longitude graticule was used to fit a simple affine transform in EPSG:4326, then the DRI pink active-fan and green inactive-fan fills were color-classified from the map image. The inset legend was masked out before polygonization. The resulting broad polygons were saved and reprojected to EPSG:5070 for raster comparison.",
        "",
        "Digitization confidence: moderate for broad active/inactive extents; low-moderate for small inactive polygons, boundaries, and map-collar/annotation-adjacent details. This is a reproducible first-pass digitization from a PDF map, not an authoritative source GIS layer.",
        "",
        "## Parcel overlap with DRI classes",
        f"- Parcel area: {fmt(overlap.get('parcel_area_m2'), 1)} m²",
    ]
    for cls in ["active", "inactive"]:
        area = overlap.get("fan_class_area_m2", {}).get(cls, 0)
        frac = overlap.get("fan_class_area_fraction", {}).get(cls, 0)
        lines.append(f"- {cls.title()} overlap: {fmt(area, 1)} m² ({fmt(100 * frac if frac is not None else None, 2)}%)")

    lines += [
        "",
        "## Roughness magnitude benchmarks",
        "| Zone | Count | Mean (m) | Std (m) | P10 | Median | P90 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label in ["active", "inactive", "parcel"]:
        s = mag[label]
        lines.append(f"| {label} | {fmt(s['count'])} | {fmt(s['mean'])} | {fmt(s['std'])} | {fmt(s['p10'])} | {fmt(s['p50'])} | {fmt(s['p90'])} |")

    lines += [
        "",
        "## Roughness scale benchmarks",
        "| Zone | Count | Mean (m) | Std (m) | P10 | Median | P90 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label in ["active", "inactive", "parcel"]:
        s = scale[label]
        lines.append(f"| {label} | {fmt(s['count'])} | {fmt(s['mean'])} | {fmt(s['std'])} | {fmt(s['p10'])} | {fmt(s['p50'])} | {fmt(s['p90'])} |")

    active_mean = mag["active"]["mean"]
    inactive_mean = mag["inactive"]["mean"]
    parcel_mean = mag["parcel"]["mean"]
    lines += [
        "",
        "## Interpretation",
    ]
    if active_mean is not None and inactive_mean is not None:
        diff = active_mean - inactive_mean
        direction = "higher" if diff > 0 else "lower"
        lines.append(
            f"- Within the local roughness-raster footprint, the digitized active DRI zone has {direction} mean multiscale roughness than the digitized inactive zone by {fmt(abs(diff))} m. Frankel & Dolan (2007) predict active fans are rougher than older inactive surfaces; this local comparison is therefore {'consistent with' if diff > 0 else 'not consistent with'} that expectation."
        )
    else:
        lines.append("- The active/inactive benchmark could not be fully computed because one class did not overlap the local roughness raster after digitization.")
    if parcel_mean is not None:
        lines.append(f"- The parcel mean roughness is {fmt(parcel_mean)} m. Compare this against the active/inactive means above as a local benchmark, not a calibrated flood-depth or regulatory hazard metric.")
    lines += [
        "- The DRI overlay is useful as independent geomorphic context. It should not be treated as a replacement for FEMA alluvial-fan flood hazard mapping or a hydraulic model.",
        "",
        "## Georeferencing diagnostics",
        f"- Render DPI: {georef['render_dpi']}",
        f"- Image size: {georef['image_size_px'][0]} x {georef['image_size_px'][1]} px",
        f"- Max longitude fit residual: {georef['max_abs_lon_fit_residual_deg']:.8f}°",
        f"- Max latitude fit residual: {georef['max_abs_lat_fit_residual_deg']:.8f}°",
        f"- Classified active pixels: {georef['active_pixels']:,}",
        f"- Classified inactive pixels: {georef['inactive_pixels']:,}",
        "",
    ]
    SUMMARY_MD.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_pdf()
    render_page_20()
    active, inactive, transform, georef = classify_masks()
    zones = polygonize_zones(active, inactive, transform)
    stats = compute_stats(zones)
    stats["georeferencing"] = georef
    STATS_JSON.parent.mkdir(parents=True, exist_ok=True)
    STATS_JSON.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    write_summary(stats, georef)
    print(json.dumps({"zones": rel(ZONES_4326), "stats": rel(STATS_JSON), "summary": rel(SUMMARY_MD)}, indent=2))


if __name__ == "__main__":
    main()
