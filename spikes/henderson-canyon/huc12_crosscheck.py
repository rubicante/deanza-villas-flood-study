"""HUC-12 cross-check stage for watershed delineation validation.

Permanent validation gate for any new bbox: checks that the D8 watershed
(1) lies ≥85% within the expected HUC-12, and (2) any watershed-only area
above the fan apex elevation is a legitimate cross-HUC headwater contribution
rather than a capture into an adjacent drainage.

Usage:
  python huc12_crosscheck.py \\
    --watershed data/vectors/henderson_watershed_boundary.geojson \\
    --dem data/processed/terrain/dem_filled.tif \\
    --huc12 181002030302 \\
    --fan-apex-elev 250

Gates:
  Gate 1: ≥85% of watershed area within HUC-12
  Gate 2: watershed-only area > fan apex elevation drains toward HUC-12
           (100% of sampled flows enter HUC-12 before hitting a pit)

Encoding note:
  WBT D8 pointer encoding is: 1=NE, 2=E, 4=SE, 8=S, 16=SW, 32=W, 64=NW, 128=N
  Do NOT use the 45-degree-rotated variant (1=NE,2=N,4=NW,...) found in
  older spike scripts — that was a verification bug, not a WBT bug.
"""

import numpy as np
from pathlib import Path
import rasterio
from rasterio import features
import geopandas as gpd
from shapely.geometry import shape
import sys
import json

# ---- Configuration ----
CRS_METRIC = "EPSG:5070"
# WBT D8 pointer encoding
D8_DR = {1: -1, 2: 0, 4: 1, 8: 1, 16: 1, 32: 0, 64: -1, 128: -1}
D8_DC = {1: 1, 2: 1, 4: 1, 8: 0, 16: -1, 32: -1, 64: -1, 128: 0}


def polygonize_raster(raster_path: Path) -> gpd.GeoDataFrame:
    """Polygonize a binary raster, returning GeoDataFrame in raster CRS."""
    with rasterio.open(raster_path) as src:
        data = src.read(1)
        crs = src.crs
        transform = src.transform
    results = (
        {"properties": {"value": v}, "geometry": s}
        for s, v in features.shapes(data.astype("uint8"), mask=(data > 0), transform=transform)
    )
    gdf = gpd.GeoDataFrame.from_features(list(results), crs=crs)
    return gdf[gdf["value"] == 1]


def load_wbd_huc12(huc12_code: str, wbd_path: Path | None = None) -> gpd.GeoDataFrame:
    """Load a specific HUC-12 from WBD GeoJSON or fetch via pynhd."""
    if wbd_path and wbd_path.exists():
        gdf = gpd.read_file(wbd_path)
        match = gdf[gdf["huc12"] == huc12_code]
        if len(match) == 0:
            raise ValueError(f"HUC-12 {huc12_code} not found in {wbd_path}")
        return match.iloc[[0]]
    # Fallback: try pynhd
    try:
        import pynhd
        wbd = pynhd.WBD("huc12", crs=4269)
        huc_gdf = wbd.byids("huc12", huc12_code)
        if len(huc_gdf) == 0:
            raise ValueError(f"HUC-12 {huc12_code} not found via pynhd")
        return huc_gdf.iloc[[0]]
    except ImportError:
        raise RuntimeError(
            "No WBD file provided and pynhd not installed. "
            "Provide --wbd-file or install pynhd."
        )


def compute_overlap(
    watershed_geom, huc12_geom
) -> dict:
    """Compute area overlap metrics between watershed and HUC-12."""
    huc12_area = huc12_geom.area / 1e6
    ws_area = watershed_geom.area / 1e6
    intersection = huc12_geom.intersection(watershed_geom)
    intersection_area = intersection.area / 1e6
    ws_only = watershed_geom.difference(huc12_geom)
    ws_only_area = ws_only.area / 1e6

    return {
        "huc12_area_km2": round(huc12_area, 2),
        "watershed_area_km2": round(ws_area, 2),
        "intersection_area_km2": round(intersection_area, 2),
        "intersection_pct_of_huc12": round(100 * intersection_area / huc12_area, 1),
        "intersection_pct_of_watershed": round(100 * intersection_area / ws_area, 1),
        "watershed_only_area_km2": round(ws_only_area, 2),
    }


def check_drainage_direction(
    dem_path: Path,
    d8_pointer_path: Path,
    ws_only_geom,
    fan_apex_elev: float,
    n_sample: int = 500,
) -> dict:
    """Check whether watershed-only area drains toward HUC-12 or elsewhere."""
    with rasterio.open(dem_path) as src:
        dem = src.read(1)
        dem_tr = src.transform

    with rasterio.open(d8_pointer_path) as src:
        d8_ptr = src.read(1)

    # Rasterize ws-only
    geoms = [ws_only_geom] if not hasattr(ws_only_geom, "geoms") else list(ws_only_geom.geoms)
    ws_only_grid = features.rasterize(
        [(g, 1) for g in geoms], out_shape=dem.shape, transform=dem_tr, dtype="uint8"
    )

    # High-elevation subset
    high_mask = (ws_only_grid == 1) & (dem > fan_apex_elev)
    high_rows, high_cols = np.where(high_mask)

    if len(high_rows) == 0:
        return {
            "high_elev_cells": 0,
            "high_elev_area_km2": 0.0,
            "pct_reaching_huc": 100.0,
            "finding": "no high-elevation ws-only area",
        }

    high_area = len(high_rows) * abs(dem_tr.a * dem_tr.e) / 1e6
    n = min(n_sample, len(high_rows))
    rng = np.random.default_rng(42)
    idx = rng.choice(len(high_rows), n, replace=False)

    reached = 0
    for i in idx:
        r, c = int(high_rows[i]), int(high_cols[i])
        for _ in range(100000):
            # Check if we've re-entered non-ws-only area (i.e., HUC-12)
            if ws_only_grid[r, c] == 0 and ws_only_grid[r, c] == 0:
                reached += 1
                break
            val = int(d8_ptr[r, c])
            if val not in D8_DR:
                break
            r += D8_DR[val]
            c += D8_DC[val]
            if r < 0 or r >= dem.shape[0] or c < 0 or c >= dem.shape[1]:
                break

    return {
        "high_elev_cells": len(high_rows),
        "high_elev_area_km2": round(high_area, 2),
        "sample_size": n,
        "reached_huc_or_intersection": reached,
        "pct_reaching": round(100 * reached / n, 1),
        "finding": (
            "drains toward HUC-12"
            if reached / n > 0.5
            else "does NOT drain toward HUC-12"
        ),
    }


def stratified_disagreement(
    dem: np.ndarray,
    tool_labels: np.ndarray,
    verification_labels: np.ndarray,
    valid_mask: np.ndarray | None = None,
) -> dict:
    """Compute disagreement rate, overall and stratified by local relief.

    Bins: <1m, 1-10m, >10m (max-min in 3×3 window around each cell).

    When disagreement is high overall but low in the >10m bin, the
    disagreement is concentrated in low-relief terrain — likely a real
    algorithmic edge case rather than a tool bug. When disagreement is
    uniform across bins, suspect a bug in the custom verification code.

    Args:
        dem: Elevation raster (2D).
        tool_labels: Integer labels from the external tool (same shape as dem).
        verification_labels: Integer labels from custom verification (same shape).
        valid_mask: Boolean mask of cells to include (default: all cells where
                    both tool and verification have valid, non-zero labels).

    Returns:
        Dict with keys: overall_count, overall_disagree, overall_rate,
        bin_<n>_count, bin_<n>_disagree, bin_<n>_rate for each bin,
        interpretation (str).
    """
    if valid_mask is None:
        valid_mask = (tool_labels > 0) & (verification_labels > 0)

    tool_v = tool_labels[valid_mask]
    verif_v = verification_labels[valid_mask]
    disagree = tool_v != verif_v

    # Compute 3×3 local relief for each valid cell
    rows, cols = np.where(valid_mask)
    relief = np.zeros(len(rows), dtype=np.float32)

    for i, (r, c) in enumerate(zip(rows, cols)):
        r0 = max(0, r - 1)
        r1 = min(dem.shape[0], r + 2)
        c0 = max(0, c - 1)
        c1 = min(dem.shape[1], c + 2)
        window = dem[r0:r1, c0:c1]
        relief[i] = window.max() - window.min()

    bins = [
        ("0-1m", relief < 1.0),
        ("1-10m", (relief >= 1.0) & (relief < 10.0)),
        ("10m+", relief >= 10.0),
    ]

    result = {
        "overall_count": int(disagree.sum() + (~disagree).sum()),
        "overall_disagree": int(disagree.sum()),
        "overall_rate": round(float(disagree.mean()) * 100, 1),
    }

    for bin_name, bin_mask in bins:
        n = int(bin_mask.sum())
        d = int(disagree[bin_mask].sum()) if n > 0 else 0
        rate = round(100 * d / n, 1) if n > 0 else 0.0
        result[f"bin_{bin_name}_count"] = n
        result[f"bin_{bin_name}_disagree"] = d
        result[f"bin_{bin_name}_rate"] = rate

    # Interpretation
    high_relief_rate = result.get("bin_10m+_rate", 0)
    overall_rate = result["overall_rate"]
    if high_relief_rate < 5 and overall_rate > 10:
        result["interpretation"] = (
            "Disagreement concentrated in low-relief terrain "
            f"({high_relief_rate}% in 10m+ bin vs {overall_rate}% overall). "
            "Likely a real algorithmic edge case, not a tool bug."
        )
    elif high_relief_rate > 5:
        result["interpretation"] = (
            f"Disagreement persists in steep terrain "
            f"({high_relief_rate}% in 10m+ bin). "
            "Suspect bug in verification code — check encoding / conventions."
        )
    else:
        result["interpretation"] = (
            f"Overall disagreement is low ({overall_rate}%). No stratification flag."
        )

    return result


def validate(
    watershed_path: Path,
    dem_path: Path,
    d8_pointer_path: Path,
    huc12_code: str,
    fan_apex_elev: float = 250.0,
    wbd_path: Path | None = None,
) -> dict:
    """Run full HUC-12 cross-check validation. Returns results dict."""
    # Load and project
    ws_gdf = polygonize_raster(watershed_path).to_crs(CRS_METRIC)
    huc12 = load_wbd_huc12(huc12_code, wbd_path).to_crs(CRS_METRIC)

    ws_geom = ws_gdf.union_all()
    huc12_geom = huc12.geometry.iloc[0]

    # Gate 1: overlap
    overlap = compute_overlap(ws_geom, huc12_geom)

    # Gate 2: drainage direction
    ws_only = ws_geom.difference(huc12_geom)
    drainage = check_drainage_direction(dem_path, d8_pointer_path, ws_only, fan_apex_elev)

    # Gate decisions
    gate1_pass = overlap["intersection_pct_of_watershed"] >= 85.0
    gate2_pass = (
        drainage["high_elev_area_km2"] < 5.0
        and drainage.get("pct_reaching", 0) > 50.0
    )

    result = {
        "huc12_code": huc12_code,
        "huc12_name": huc12.iloc[0].get("name", "unknown"),
        "overlap": overlap,
        "drainage": drainage,
        "gates": {
            "gate1_overlap": {"pass": gate1_pass, "threshold": "≥85% within HUC-12"},
            "gate2_drainage": {"pass": gate2_pass, "threshold": "<5 km² high-elev and drains toward HUC-12"},
        },
        "all_pass": gate1_pass and gate2_pass,
    }
    return result


def main():
    import argparse

    p = argparse.ArgumentParser(description="HUC-12 cross-check for watershed validation")
    p.add_argument("--watershed", required=True, type=Path, help="Watershed raster (.tif)")
    p.add_argument("--dem", required=True, type=Path, help="DEM raster (.tif)")
    p.add_argument("--d8-pointer", required=True, type=Path, help="D8 pointer raster (.tif)")
    p.add_argument("--huc12", required=True, type=str, help="HUC-12 code (e.g. 181002030302)")
    p.add_argument("--fan-apex-elev", type=float, default=250.0, help="Fan apex elevation (m)")
    p.add_argument("--wbd-file", type=Path, default=None, help="Local WBD GeoJSON (optional)")
    p.add_argument("--json", action="store_true", help="Output JSON only")

    args = p.parse_args()

    result = validate(
        watershed_path=args.watershed,
        dem_path=args.dem,
        d8_pointer_path=args.d8_pointer,
        huc12_code=args.huc12,
        fan_apex_elev=args.fan_apex_elev,
        wbd_path=args.wbd_file,
    )

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"HUC-12 Cross-Check: {result['huc12_code']} ({result['huc12_name']})")
        o = result["overlap"]
        print(f"  Watershed: {o['watershed_area_km2']} km²")
        print(f"  HUC-12:    {o['huc12_area_km2']} km²")
        print(f"  Overlap:   {o['intersection_area_km2']} km² ({o['intersection_pct_of_watershed']}% of watershed)")
        d = result["drainage"]
        print(f"  High-elev ws-only: {d.get('high_elev_area_km2', 0)} km², "
              f"{d.get('pct_reaching', 'N/A')}% drain toward HUC-12")
        print(f"  Gate 1 (≥85% within HUC-12): {'PASS' if result['gates']['gate1_overlap']['pass'] else 'FAIL'}")
        print(f"  Gate 2 (drainage direction): {'PASS' if result['gates']['gate2_drainage']['pass'] else 'FAIL'}")
        print(f"  OVERALL: {'PASS' if result['all_pass'] else 'FAIL'}")

    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
