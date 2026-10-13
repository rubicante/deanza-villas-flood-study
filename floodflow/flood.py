"""`floodflow flood`: 2D rain-on-grid design-storm run for one parcel.

    domain  = parcel ⊕ --buffer metres, plus its whole upstream catchment
    terrain = raw 1m lidar (NOT hydro-conditioned: depressions are real
              storage in a 2D model), averaged to --res, lidar holes filled
    storm   = NOAA Atlas 14 --ari / --duration, alternating-block hyetograph
    solver  = hydraulics.py (local inertial), rain on every domain cell,
              free outfalls round the domain edge

Writes to data/derived/runs/<parcel>/flood/<tag>/: max depth, max speed,
max depth×speed, time of max depth (GeoTIFF, EPSG:5070), and summary.json
with the parcel's depth statistics and a FEMA flood-zone comparison.

The parcel's own traced contributing area comes from single-direction
routing, and 2D flow on a fan can cross it (the first Villas run showed a
wash from outside it flooding the parcel's east side). Tracing upstream of
the buffered parcel brings in every catchment that can reach its surroundings.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.fill import fillnodata
from rasterio.warp import Resampling, reproject

from floodflow.config import BOOTSTRAP_BUFFER_M, DEFAULT_PARCEL, PARCELS, TARGET_CRS, Layout
from floodflow.dinf import compute_dinf
from floodflow.fetch import fetch_dem_1m, fetch_dem_10m, read_provenance
from floodflow.geo import polygon_mask
from floodflow.hydraulics import Grid, SolverParams, mass_balance, simulate
from floodflow.preprocess import preprocess_dem
from floodflow.storm import alternating_block, atlas14
from floodflow.upstream import contributing_area

DEPTH_THRESHOLDS_M = (0.05, 0.15, 0.30, 0.60)   # ~2 in, 6 in, 1 ft, 2 ft
FT = 0.3048


@dataclass(frozen=True)
class FloodParams:
    ari_years: int = 100
    duration_min: int = 60
    resolution_m: float = 8.0            # CFL-converged at θ = 1; ≤4 m surges on steep chutes
    manning_n: float = 0.045
    buffer_m: float = 300.0
    margin_m: float = 1000.0
    initial_loss_mm: float = 0.0
    loss_rate_mm_h: float = 0.0
    after_storm_min: int = 60
    peak_frac: float = 0.5
    channel_n: float | None = None       # n on steep channels (see `channel_mask`)

    @property
    def tag(self) -> str:
        loss = (f"_il{self.initial_loss_mm:g}cl{self.loss_rate_mm_h:g}"
                if self.initial_loss_mm or self.loss_rate_mm_h else "")
        ch = f"_ch{self.channel_n:g}" if self.channel_n is not None else ""
        peak = f"_pk{self.peak_frac:g}" if self.peak_frac != 0.5 else ""
        after = f"_after{self.after_storm_min}" if self.after_storm_min != 60 else ""
        return (f"ari{self.ari_years}_{self.duration_min}min_{self.resolution_m:g}m"
                f"_n{self.manning_n:g}{ch}{loss}{peak}{after}")

    def solver(self) -> SolverParams:
        return SolverParams(manning_n=self.manning_n,
                            initial_loss=self.initial_loss_mm * 1e-3,
                            loss_rate=self.loss_rate_mm_h * 1e-3 / 3600)


def domain(layout: Layout, buffer_m: float, work: Path,
           margin_m: float = 1000.0) -> gpd.GeoDataFrame:
    """Parcel ⊕ buffer, plus everything upstream of it (10m D∞ trace on a
    breach-filled bootstrap DEM, as in `prepare`), plus parcel ⊕ `margin_m`
    so the outfalls sit well away from the parcel (a boundary 350 m
    downslope visibly backed water up toward it).

    Tracing the buffered parcel, not buffering the parcel's own contributing
    area, means any wash that can reach the area around the parcel brings
    its whole catchment into the model."""
    cached = work / f"domain_buffer{buffer_m:g}_margin{margin_m:g}.geojson"
    if cached.exists():
        return gpd.read_file(cached)
    parcel = gpd.read_file(layout.boundary).to_crs(TARGET_CRS)
    target = gpd.GeoDataFrame(geometry=[parcel.union_all().buffer(buffer_m)], crs=TARGET_CRS)
    boot = work / "bootstrap"
    boot.mkdir(parents=True, exist_ok=True)
    dem_raw, dem_filled = boot / "dem_10m.tif", boot / "dem_10m_filled.tif"
    ptr = boot / "dinf_pointer_10m.tif"
    print("  domain: tracing upstream of the buffered parcel (10m D∞)")
    fetch_dem_10m(gpd.GeoDataFrame(geometry=target.buffer(BOOTSTRAP_BUFFER_M), crs=TARGET_CRS),
                  output=dem_raw)
    preprocess_dem(dem_raw, output=dem_filled, strategy="breach_then_fill")
    compute_dinf(dem_filled, output=boot / "dinf_accum_10m.tif", pointer=ptr)
    upstream = contributing_area(ptr, target).to_crs(TARGET_CRS)
    geom = (upstream.union_all().union(target.union_all()).buffer(50.0)
            .union(parcel.union_all().buffer(margin_m)))
    dom = gpd.GeoDataFrame({"area_km2": [round(geom.area / 1e6, 3)]}, geometry=[geom],
                           crs=TARGET_CRS)
    dom.to_file(cached, driver="GeoJSON")
    shutil.rmtree(boot)
    return dom


def terrain(layout: Layout, dom: gpd.GeoDataFrame, params: FloodParams, work: Path):
    """Raw 1m lidar over the domain, averaged to the model resolution.
    Returns (z with NaN outside the domain, rasterio profile)."""
    dem_1m = work / f"dem_1m_domain_buffer{params.buffer_m:g}_margin{params.margin_m:g}.tif"
    if not dem_1m.exists():
        fetch_dem_1m(dom, output=dem_1m, crs=TARGET_CRS)
    with rasterio.open(dem_1m) as src:
        prof = src.profile.copy()
        z1 = src.read(1, masked=True).filled(np.nan).astype(np.float64)
    res = params.resolution_m
    if res != 1.0:
        f = int(round(res))
        if f != res:
            raise ValueError("resolution must be a whole number of metres")
        ny, nx = z1.shape[0] // f, z1.shape[1] // f
        t = prof["transform"]
        transform = rasterio.Affine(res, 0, t.c, 0, -res, t.f)
        z = np.full((ny, nx), np.nan)
        reproject(z1, z, src_transform=t, src_crs=prof["crs"], dst_transform=transform,
                  dst_crs=prof["crs"], src_nodata=np.nan, dst_nodata=np.nan,
                  resampling=Resampling.average)
        prof.update(transform=transform, height=ny, width=nx)
    else:
        z = z1
    inside = polygon_mask(dom, prof["crs"], prof["transform"], z.shape).astype(bool)
    holes = inside & ~np.isfinite(z)
    if holes.any():
        print(f"  filling {holes.sum()} lidar-hole cells ({holes.sum() / inside.sum():.3%})")
        z = fillnodata(np.where(np.isfinite(z), z, 0.0), mask=np.isfinite(z).astype(np.uint8),
                       max_search_distance=200)
    z = np.where(inside, z, np.nan)
    prof.update(dtype="float32", nodata=np.nan, compress="lzw", count=1)
    return z, prof, dem_1m


def _write(path: Path, data: np.ndarray, prof: dict, active: np.ndarray) -> None:
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(np.where(active, data, np.nan).astype("float32"), 1)


def _depth_stats(h: np.ndarray, cell_area: float) -> dict:
    if h.size == 0:
        return {}
    return {
        "area_m2": float(h.size * cell_area),
        "depth_m": {f"p{p}": round(float(np.percentile(h, p)), 3) for p in (50, 90, 99)}
        | {"max": round(float(h.max()), 3)},
        "fraction_deeper_than": {f"{t:g}m": round(float((h >= t).mean()), 4)
                                 for t in DEPTH_THRESHOLDS_M},
    }


def summarise(layout: Layout, prof: dict, grid: Grid, state, params: FloodParams) -> dict:
    act = grid.active == 1
    cell_area = grid.dx ** 2
    parcel = polygon_mask(layout.boundary, prof["crs"], prof["transform"], act.shape).astype(bool)
    in_parcel = parcel & act
    out = {"parcel": _depth_stats(state.h_max[in_parcel], cell_area)}
    if in_parcel.any():
        out["parcel"]["speed_max_ms"] = round(float(state.v_max[in_parcel].max()), 2)
        out["parcel"]["depth_x_speed_max_m2s"] = round(float(state.dv_max[in_parcel].max()), 3)
        wet = in_parcel & (state.h_max >= 0.15)
        if wet.any():
            out["parcel"]["time_of_max_depth_min_median"] = round(
                float(np.median(state.t_hmax[wet])) / 60, 1)

    fema_path = layout.publish_root / "nfhl_borrego_valley.geojson"
    if fema_path.exists():
        fema = gpd.read_file(fema_path).to_crs(TARGET_CRS)
        zones = []
        for _, z in fema.iterrows():
            m = polygon_mask(gpd.GeoDataFrame(geometry=[z.geometry], crs=TARGET_CRS),
                             prof["crs"], prof["transform"], act.shape).astype(bool)
            both = m & act
            if both.sum() * cell_area < 1000:        # ignore slivers < 0.1 ha
                continue
            zone = {"zone": z.FLD_ZONE, "id": z.FLD_AR_ID,
                    "fema_depth_m": round(z.DEPTH * FT, 2) if z.DEPTH and z.DEPTH > 0 else None,
                    "zone_area_in_domain_frac": round(float(both.sum() * cell_area
                                                            / z.geometry.area), 3),
                    "in_parcel_m2": float((both & parcel).sum() * cell_area),
                    **_depth_stats(state.h_max[both], cell_area)}
            zones.append(zone)
        outside = act & ~polygon_mask(fema[fema.SFHA_TF == "T"], prof["crs"],
                                      prof["transform"], act.shape).astype(bool)
        out["fema_zones"] = zones
        out["outside_sfha"] = _depth_stats(state.h_max[outside], cell_area)
    return out


def channel_mask(z: np.ndarray, dx: float, reference: Path,
                 min_depth_m: float = 0.3, min_slope: float = 0.05) -> np.ndarray:
    """Steep channels: cells that `reference` (a max_depth.tif on the same
    grid, normally the default-parameter run) floods ≥ `min_depth_m` on
    slopes ≥ `min_slope`. Bare-earth lidar has no roughness map, and the
    boulder canyons above the fan are where n = 0.045 is too smooth
    (~11 m/s at 1 m depth); the sandy fan washes are left at the base n."""
    if not reference.exists():
        raise FileNotFoundError(f"{reference} not found: run `floodflow flood` with the "
                                "default parameters first")
    with rasterio.open(reference) as src:
        h = src.read(1)
    if h.shape != z.shape:
        raise ValueError(f"{reference} is {h.shape}, the grid is {z.shape}")
    gy, gx = np.gradient(np.where(np.isfinite(z), z, np.nan), dx)
    slope = np.hypot(gx, gy)
    return (np.nan_to_num(h) >= min_depth_m) & (np.nan_to_num(slope) >= min_slope)


@dataclass
class Inputs:
    """Everything a run needs before the solver: built once, shared by a batch."""
    z: np.ndarray
    prof: dict
    dem_1m: Path
    storm: object                   # storm.PFTable

    def blocks(self, params: FloodParams) -> np.ndarray:
        return alternating_block(self.storm, params.ari_years, params.duration_min,
                                 peak_frac=params.peak_frac)


def inputs(layout: Layout, params: FloodParams) -> Inputs:
    """Domain, terrain and the Atlas 14 table (depend only on parcel, buffer,
    margin and resolution)."""
    work = layout.run_dir / "flood"
    work.mkdir(parents=True, exist_ok=True)
    dom = domain(layout, params.buffer_m, work, params.margin_m)
    print(f"  domain: {dom.area.sum() / 1e6:.2f} km²")
    z, prof, dem_1m = terrain(layout, dom, params, work)
    centroid = gpd.read_file(layout.boundary).to_crs("EPSG:4326").union_all().centroid
    pf = atlas14(round(centroid.y, 4), round(centroid.x, 4), layout.root / "data" / "raw" / "storm")
    return Inputs(z, prof, dem_1m, pf)


def grid_for(layout: Layout, params: FloodParams, inp: Inputs) -> Grid:
    n: float | np.ndarray = params.manning_n
    if params.channel_n is not None:
        ref = layout.run_dir / "flood" / FloodParams(resolution_m=params.resolution_m,
                                                     buffer_m=params.buffer_m,
                                                     margin_m=params.margin_m).tag
        mask = channel_mask(inp.z, params.resolution_m, ref / "max_depth.tif")
        print(f"  channels: {mask.sum()} cells at n = {params.channel_n:g} "
              f"({mask.sum() * params.resolution_m ** 2 / 1e4:.1f} ha)")
        n = np.where(mask, params.channel_n, params.manning_n)
    return Grid(inp.z, params.resolution_m, manning_n=n)


def finish(layout: Layout, params: FloodParams, inp: Inputs, grid: Grid, state,
           where: str, wall_s: float) -> dict:
    """Write the rasters and summary.json for one finished run."""
    out_dir = layout.run_dir / "flood" / params.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    prof, blocks = inp.prof, inp.blocks(params)
    act = grid.active == 1
    _write(out_dir / "max_depth.tif", state.h_max, prof, act)
    _write(out_dir / "max_speed.tif", state.v_max, prof, act)
    _write(out_dir / "max_depth_x_speed.tif", state.dv_max, prof, act)
    _write(out_dir / "time_of_max_depth_min.tif", state.t_hmax / 60, prof, act)
    _write(out_dir / "terrain.tif", grid.z, prof, act)

    mb = mass_balance(grid, state)
    summary = {
        "parcel": layout.parcel.key,
        "params": asdict(params),
        "solver": asdict(params.solver()),
        "storm": {"source": inp.storm.source, "total_mm": round(float(blocks.sum() * 300e3), 2),
                  "block_min": 5, "rain_mm_per_block": (blocks * 300e3).round(2).tolist()},
        "grid": {"shape": list(inp.z.shape), "active_cells": grid.n_active,
                 "resolution_m": params.resolution_m},
        "dem": read_provenance(inp.dem_1m),
        "run": {"steps": state.steps, "sim_minutes": state.t / 60,
                "where": where, "wall_seconds": round(wall_s, 1)},
        "mass_balance": {k: round(v, 3) if k != "error_rel" else v for k, v in mb.items()},
        **summarise(layout, prof, grid, state, params),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    p = summary["parcel"]
    print(f"  {params.tag}: parcel p50 {p['depth_m']['p50']} m, p90 {p['depth_m']['p90']} m, "
          f"max {p['depth_m']['max']} m; ≥0.3 m over {p['fraction_deeper_than']['0.3m']:.1%}"
          f" → {out_dir}")
    return summary


def run(layout: Layout, params: FloodParams, remote_cpu: int | None = None) -> dict:
    """`remote_cpu` runs the solver on a Modal machine with that many cores."""
    t0 = time.time()
    print(f"=== flood: {layout.parcel.name}, {params.tag} ===")
    inp = inputs(layout, params)
    blocks = inp.blocks(params)
    print(f"  storm: {params.ari_years}-yr {params.duration_min}-min, "
          f"{blocks.sum() * 300e3:.1f} mm, peak {blocks.max() * 3.6e6:.0f} mm/h (5-min)")
    grid = grid_for(layout, params, inp)
    print(f"  grid: {inp.z.shape[1]}×{inp.z.shape[0]} at {params.resolution_m:g} m, "
          f"{grid.n_active / 1e6:.2f}M active cells ({grid.n_active * grid.dx ** 2 / 1e6:.2f} km²)")
    if remote_cpu:
        from floodflow import remote
        state = remote.simulate(grid, blocks, 300.0, params.after_storm_min * 60.0,
                                params.solver(), inp.z, cpu=remote_cpu)
    else:
        state = simulate(grid, blocks, block_s=300.0, t_after=params.after_storm_min * 60.0,
                         params=params.solver())
    return finish(layout, params, inp, grid, state,
                  f"modal, {remote_cpu} cores" if remote_cpu else "local", time.time() - t0)


def main(argv: list[str] | None = None) -> int:
    d = FloodParams()
    ap = argparse.ArgumentParser(prog="floodflow flood", description=__doc__.split("\n\n")[0])
    ap.add_argument("--parcel", choices=list(PARCELS), default=DEFAULT_PARCEL)
    ap.add_argument("--ari", type=int, default=d.ari_years, help="Return period, years")
    ap.add_argument("--duration", type=int, default=d.duration_min, help="Storm minutes")
    ap.add_argument("--res", type=float, default=d.resolution_m, help="Grid metres")
    ap.add_argument("--n", type=float, default=d.manning_n, help="Manning's n")
    ap.add_argument("--buffer", type=float, default=d.buffer_m,
                    help="Metres round the parcel whose upstream catchment is modelled")
    ap.add_argument("--margin", type=float, default=d.margin_m,
                    help="Metres round the parcel always in the domain (keeps outfalls away)")
    ap.add_argument("--initial-loss", type=float, default=d.initial_loss_mm, help="mm")
    ap.add_argument("--loss-rate", type=float, default=d.loss_rate_mm_h, help="mm/h")
    ap.add_argument("--after", type=int, default=d.after_storm_min,
                    help="Minutes simulated after the rain stops")
    ap.add_argument("--peak", type=float, default=d.peak_frac,
                    help="Storm peak position as a fraction of its length")
    ap.add_argument("--channel-n", type=float, default=None,
                    help="Manning's n on steep channels (mask from the default-parameter run)")
    ap.add_argument("--remote", type=int, nargs="?", const=64, default=None, metavar="CPUS",
                    help="Run the solver on Modal with CPUS cores (default 64); "
                         "needs `pip install modal` and MODAL_TOKEN_ID/SECRET")
    a = ap.parse_args(argv)
    layout = Layout.for_parcel(a.parcel)
    if not layout.boundary.exists():
        layout.parcel.generate(layout.boundary)
    run(layout, FloodParams(ari_years=a.ari, duration_min=a.duration, resolution_m=a.res,
                            manning_n=a.n, buffer_m=a.buffer, margin_m=a.margin,
                            initial_loss_mm=a.initial_loss,
                            loss_rate_mm_h=a.loss_rate, after_storm_min=a.after,
                            peak_frac=a.peak, channel_n=a.channel_n),
        remote_cpu=a.remote)
    return 0
