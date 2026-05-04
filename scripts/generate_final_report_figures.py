from __future__ import annotations

"""Generate the canonical final-report figure set for the Borrego Springs flood study.

Outputs are written to outputs/figures/final_report/.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.mask import mask
from matplotlib.colors import LightSource
from PIL import Image
from scripts.study_config import ROOT, config_path, step_path

FIGDIR = ROOT / "outputs/figures/final_report"

PARCEL_BOUNDARY = config_path("paths", "parcel_boundary")
PARCEL_POLYGONS = config_path("paths", "parcel_polygons")
LOCAL_AOI = config_path("paths", "local_aoi")
CONTEXT_AOI = config_path("paths", "context_aoi")
FEMA = config_path("paths", "hazard_polygons")
STREAMS = config_path("paths", "selected_streams")
PARCHAN = step_path("parcel_overlay", "clip_gpkg")
DEM = config_path("paths", "dem_filled")
SLOPE = config_path("paths", "slope_degrees")
FAN_STATS = step_path("fan_synthesis", "stats_csv")
SWEEP = step_path("wash_extraction", "summary_csv")
VAL_JSON = step_path("satellite_validation", "selected_json")
BROWSE = None  # resolved from selected validation metadata

FIGDIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update(
    {
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "figure.dpi": 180,
        "savefig.dpi": 220,
        "font.family": "DejaVu Sans",
    }
)


def read_5070(path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    return gdf.to_crs("EPSG:5070")


def add_north_arrow(ax, x=0.96, y=0.94, size=0.075):
    ax.annotate(
        "N",
        xy=(x, y),
        xytext=(x, y - size),
        xycoords="axes fraction",
        textcoords="axes fraction",
        ha="center",
        va="center",
        fontsize=11,
        fontweight="bold",
        arrowprops=dict(arrowstyle="-|>", color="black", lw=1.2),
    )


def add_scale_bar(ax, length_m, location=(0.08, 0.06), linewidth=3):
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    x0 = xmin + (xmax - xmin) * location[0]
    y0 = ymin + (ymax - ymin) * location[1]
    ax.plot([x0, x0 + length_m], [y0, y0], color="black", lw=linewidth, solid_capstyle="butt")
    ax.plot([x0, x0], [y0 - (ymax - ymin) * 0.005, y0 + (ymax - ymin) * 0.005], color="black", lw=1)
    ax.plot([x0 + length_m, x0 + length_m], [y0 - (ymax - ymin) * 0.005, y0 + (ymax - ymin) * 0.005], color="black", lw=1)
    ax.text(x0 + length_m / 2, y0 - (ymax - ymin) * 0.02, f"{int(length_m)} m", ha="center", va="top", fontsize=9)


def save(fig, path):
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def fig1_context_overview():
    boundary = read_5070(PARCEL_BOUNDARY)
    parcels = read_5070(PARCEL_POLYGONS)
    local = read_5070(LOCAL_AOI)
    context = read_5070(CONTEXT_AOI)
    hazard = read_5070(FEMA)

    fig, ax = plt.subplots(figsize=(8.8, 7.2))
    context.plot(ax=ax, facecolor="none", edgecolor="#555555", linewidth=1.2, linestyle="--", zorder=1)
    hazard.plot(ax=ax, color="#fcae91", edgecolor="#cb181d", linewidth=0.4, alpha=0.35, zorder=2)
    parcels.plot(ax=ax, facecolor="#c6dbef", edgecolor="#6baed6", linewidth=0.5, alpha=0.35, zorder=3)
    local.plot(ax=ax, facecolor="none", edgecolor="#3182bd", linewidth=1.2, zorder=4)
    boundary.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=2.0, zorder=5)

    minx, miny, maxx, maxy = context.total_bounds
    padx = (maxx - minx) * 0.08
    pady = (maxy - miny) * 0.08
    ax.set_xlim(minx - padx, maxx + padx)
    ax.set_ylim(miny - pady, maxy + pady)
    ax.set_aspect("equal")
    ax.set_xlabel("Easting (EPSG:5070 m)")
    ax.set_ylabel("Northing (EPSG:5070 m)")
    ax.set_title("Figure 1. De Anza Villas in mapped flood context")
    add_north_arrow(ax)
    add_scale_bar(ax, 1000, location=(0.76, 0.07))

    handles = [
        plt.Line2D([0], [0], color="black", lw=2, label="De Anza Villas boundary"),
        plt.Line2D([0], [0], color="#3182bd", lw=1.5, label="2 km local AOI"),
        plt.Line2D([0], [0], color="#555555", lw=1.2, linestyle="--", label="8 km context AOI"),
        plt.Line2D([0], [0], marker="s", color="none", markerfacecolor="#fcae91", markeredgecolor="#cb181d", markersize=8, label="FEMA flood polygons"),
        plt.Line2D([0], [0], marker="s", color="none", markerfacecolor="#c6dbef", markeredgecolor="#6baed6", markersize=8, label="Parcel polygons"),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=True, framealpha=0.96, fontsize=8)
    ax.text(
        0.01,
        0.99,
        "Purpose: orient the parcel within the official flood-context and analysis footprints.",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=3),
    )
    save(fig, FIGDIR / "figure1_context_overview.png")


def fig2_terrain_drainage():
    boundary = read_5070(PARCEL_BOUNDARY)
    hazard = read_5070(FEMA)
    streams = read_5070(STREAMS)

    local = read_5070(LOCAL_AOI)
    geom = local.geometry.union_all()

    with rasterio.open(DEM) as src:
        dem_arr, dem_transform = mask(src, [geom], crop=True, filled=False)
        dem = np.array(dem_arr[0].filled(np.nan), dtype="float64")
        # Build hillshade from the cropped DEM.
        z = dem.copy()
        z[~np.isfinite(z)] = np.nan
        valid = np.isfinite(z)
        # Fill NaNs for hillshade with nearest valid value to avoid edge artifacts.
        if valid.any():
            fill = np.nanmean(z)
            z = np.where(valid, z, fill)
        ls = LightSource(azdeg=315, altdeg=45)
        shaded = ls.shade(z, cmap=plt.cm.Greys, vert_exag=1.8, blend_mode="soft")
        # Reuse crop transform for plotting.
        x0, y0 = dem_transform * (0, 0)
        x1, y1 = dem_transform * (z.shape[1], z.shape[0])
        extent = (x0, x1, y1, y0)

    fig, ax = plt.subplots(figsize=(8.8, 7.2))
    ax.imshow(shaded, extent=extent, origin="upper", zorder=0)
    hazard.plot(ax=ax, color="#fcae91", edgecolor="#cb181d", linewidth=0.35, alpha=0.20, zorder=1)

    streams[streams["hazard_len_m"] > 0].plot(ax=ax, color="#cb181d", linewidth=1.3, alpha=0.95, zorder=3)
    streams[streams["hazard_len_m"] == 0].plot(ax=ax, color="#2c7fb8", linewidth=0.8, alpha=0.8, zorder=2)
    boundary.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=1.8, zorder=4)

    minx, miny, maxx, maxy = local.total_bounds
    padx = 220
    pady = 220
    ax.set_xlim(minx - padx, maxx + padx)
    ax.set_ylim(miny - pady, maxy + pady)
    ax.set_aspect("equal")
    ax.set_xlabel("Easting (EPSG:5070 m)")
    ax.set_ylabel("Northing (EPSG:5070 m)")
    ax.set_title("Figure 2. 1 m terrain background and the selected drainage fabric")
    add_north_arrow(ax)
    add_scale_bar(ax, 500)

    handles = [
        plt.Line2D([0], [0], color="#cb181d", lw=1.8, label="Selected channels overlapping mapped hazard"),
        plt.Line2D([0], [0], color="#2c7fb8", lw=1.2, label="Selected channels outside mapped hazard"),
        plt.Line2D([0], [0], color="black", lw=2, label="De Anza Villas boundary"),
        plt.Line2D([0], [0], marker="s", color="none", markerfacecolor="#fcae91", markeredgecolor="#cb181d", markersize=8, label="FEMA flood polygons"),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=True, framealpha=0.96, fontsize=8)
    ax.text(
        0.01,
        0.99,
        "Purpose: show the terrain texture and extracted wash network that drive the active-fan interpretation.",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        bbox=dict(facecolor="white", edgecolor="none", alpha=0.83, pad=3),
    )
    save(fig, FIGDIR / "figure2_terrain_drainage.png")


def fig3_parcel_overlap():
    boundary = read_5070(PARCEL_BOUNDARY)
    parcels = read_5070(PARCEL_POLYGONS)
    hazard = read_5070(FEMA)
    parcel_streams = read_5070(PARCHAN)
    streams = read_5070(STREAMS)

    minx, miny, maxx, maxy = boundary.total_bounds
    pad = 110

    fig, ax = plt.subplots(figsize=(8.2, 7.0))
    hazard.plot(ax=ax, color="#fcae91", edgecolor="#cb181d", linewidth=0.35, alpha=0.18, zorder=1)
    parcels.plot(ax=ax, facecolor="#d9d9d9", edgecolor="#969696", linewidth=0.45, alpha=0.25, zorder=2)
    streams.plot(ax=ax, color="#9ecae1", linewidth=0.8, alpha=0.40, zorder=3)
    parcel_streams.plot(ax=ax, color="#2ca25f", linewidth=1.8, alpha=0.95, zorder=4)
    boundary.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=2.2, zorder=5)

    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad, maxy + pad)
    ax.set_aspect("equal")
    ax.set_xlabel("Easting (EPSG:5070 m)")
    ax.set_ylabel("Northing (EPSG:5070 m)")
    ax.set_title("Figure 3. Exact parcel boundary versus the selected channel network")
    add_north_arrow(ax)
    add_scale_bar(ax, 100)

    handles = [
        plt.Line2D([0], [0], color="black", lw=2.2, label="De Anza Villas complex boundary"),
        plt.Line2D([0], [0], color="#2ca25f", lw=2.0, label="Selected stream segments inside parcel boundary"),
        plt.Line2D([0], [0], color="#9ecae1", lw=1.0, label="Selected stream network"),
        plt.Line2D([0], [0], marker="s", color="none", markerfacecolor="#fcae91", markeredgecolor="#cb181d", markersize=8, label="FEMA flood polygons"),
        plt.Line2D([0], [0], marker="s", color="none", markerfacecolor="#d9d9d9", markeredgecolor="#969696", markersize=8, label="Parcel polygons"),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=True, framealpha=0.96, fontsize=8)
    ax.text(
        0.02,
        0.98,
        "Key readout: 904.6 m of selected network lies inside the parcel boundary; 96.7% of parcel-crossing channel length overlaps mapped hazard polygons.",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        bbox=dict(facecolor="white", edgecolor="none", alpha=0.88, pad=3),
    )
    save(fig, FIGDIR / "figure3_parcel_overlap.png")


def fig4_terrain_comparison():
    df = pd.read_csv(FAN_STATS)
    order = ["parcel", "local_aoi", "context_aoi"]
    labels = {"parcel": "Parcel", "local_aoi": "Local AOI", "context_aoi": "Context AOI"}
    colors = ["#2b8cbe", "#7bccc4", "#bdbdbd"]
    metrics = [
        ("stream_density_m_per_km2", "Stream density (m/km²)", "higher = more concentrated drainage"),
        ("relief_p95_p5_m", "Relief p95–p5 (m)", "local topographic range"),
        ("slope_mean_deg", "Mean slope (degrees)", "terrain steepness"),
        ("rough_mean_m", "Mean roughness (m)", "multiscale surface roughness"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(10.2, 7.8))
    axes = axes.ravel()
    for ax, (col, title, subtitle) in zip(axes, metrics):
        vals = [float(df.loc[df["area_name"] == o, col].iloc[0]) for o in order]
        bars = ax.bar(range(len(order)), vals, color=colors, width=0.68, edgecolor="white", linewidth=0.8)
        ax.set_xticks(range(len(order)), [labels[o] for o in order])
        ax.set_title(title)
        ax.grid(axis="y", color="#dddddd", linewidth=0.7)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{v:.1f}", ha="center", va="bottom", fontsize=8)
        ax.text(0.02, 0.96, subtitle, transform=ax.transAxes, ha="left", va="top", fontsize=8, color="#444444")
    axes[0].set_ylabel("m per km²")
    axes[1].set_ylabel("m")
    axes[2].set_ylabel("degrees")
    axes[3].set_ylabel("m")
    fig.suptitle("Figure 4. Parcel vs local AOI vs context terrain comparison", y=0.98, fontsize=13)
    fig.text(0.5, 0.01, "All values are taken from fan-synthesis outputs at the selected 5000-cell stream threshold.", ha="center", fontsize=9)
    fig.tight_layout(rect=[0.03, 0.04, 1, 0.96])
    save(fig, FIGDIR / "figure4_terrain_comparison.png")


def fig5_satellite_validation():
    import json
    meta = json.loads(VAL_JSON.read_text())
    if isinstance(meta, list):
        meta = meta[0]
    img = Image.open(Path(meta["browse_path"])).convert("RGB")
    fig = plt.figure(figsize=(11.2, 6.8))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.45, 1.0], wspace=0.05)
    ax_img = fig.add_subplot(gs[0, 0])
    ax_text = fig.add_subplot(gs[0, 1])
    ax_img.imshow(img)
    ax_img.set_axis_off()
    ax_img.set_title("2023-08-22 OPERA DSWx-HLS browse image", fontsize=12, pad=10)

    ax_text.set_axis_off()
    ax_text.set_title("Figure 5. Satellite validation summary", fontsize=12, pad=10)
    lines = [
        ("Selected scene", meta.get("date", "2023-08-22")),
        ("Collection", meta.get("collection", "OPERA DSWx-HLS")),
        ("Local water pixels", f"{meta.get('local_water_pixels', 0):,}"),
        ("Parcel water pixels", f"{meta.get('parcel_water_pixels', 0):,}"),
        ("Overall water pixels", f"{meta.get('water_pixels', 0):,}"),
        ("Local water share", f"{100 * meta.get('local_water_share', 0.0):.2f}%"),
        ("Parcel water share", f"{100 * meta.get('parcel_water_share', 0.0):.2f}%"),
        ("Overall water share", f"{100 * meta.get('overall_water_share', 0.0):.2f}%"),
    ]
    y = 0.92
    for label, value in lines:
        ax_text.text(0.04, y, label, ha="left", va="top", fontsize=10, fontweight="bold", transform=ax_text.transAxes)
        ax_text.text(0.62, y, value, ha="left", va="top", fontsize=10, transform=ax_text.transAxes)
        y -= 0.09
    ax_text.text(
        0.04,
        0.15,
        "Interpretation: the HLS scene contains positive local wetting evidence. The later S1 scene did not show local AOI water pixels, which is treated as weak absence evidence only.",
        ha="left",
        va="top",
        fontsize=9.5,
        transform=ax_text.transAxes,
        wrap=True,
        bbox=dict(facecolor="#f7f7f7", edgecolor="#cccccc", boxstyle="round,pad=0.5"),
    )
    ax_text.text(
        0.04,
        0.03,
        "Browse render cue: blue tones mark detected surface water; the black wedge is masked/no-data in the browse rendering.",
        ha="left",
        va="bottom",
        fontsize=8.5,
        transform=ax_text.transAxes,
        wrap=True,
        color="#444444",
    )
    fig.tight_layout(rect=[0.02, 0.03, 0.98, 0.98])
    save(fig, FIGDIR / "figure5_satellite_validation.png")


def fig6_threshold_justification():
    df = pd.read_csv(SWEEP)
    df = df.sort_values("threshold_cells")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.4, 7.4), sharex=True, gridspec_kw={"height_ratios": [1.05, 0.95]})

    ax1.plot(df["threshold_cells"], df["hazard_share"], marker="o", color="#cb181d", lw=1.8, label="Hazard share")
    ax1.plot(df["threshold_cells"], df["local_aoi_share"], marker="o", color="#3182bd", lw=1.6, label="Local AOI share")
    ax1.plot(df["threshold_cells"], df["context_share"], marker="o", color="#636363", lw=1.6, label="Context AOI share")
    ax1.axvline(5000, color="#222222", linestyle="--", lw=1.2)
    ax1.scatter([5000], [float(df.loc[df["threshold_cells"] == 5000, "hazard_share"].iloc[0])], s=60, color="#cb181d", zorder=5)
    ax1.annotate(
        "Selected\n5000 cells",
        xy=(5000, 0.98),
        xycoords="data",
        xytext=(4300, 0.88),
        textcoords="data",
        fontsize=8.5,
        ha="left",
        va="center",
        arrowprops=dict(arrowstyle="->", color="#222222", lw=1.0),
        bbox=dict(facecolor="white", edgecolor="#cccccc", boxstyle="round,pad=0.25"),
    )
    ax1.set_ylabel("Share of network length")
    ax1.set_ylim(0, 1.05)
    ax1.grid(True, axis="y", color="#dddddd", linewidth=0.7)
    ax1.legend(loc="lower right", frameon=True, fontsize=8)
    ax1.set_title("Figure 6. Why the 5000-cell stream threshold was selected")
    ax1.text(0.02, 0.05, "Vertical dashed line marks the chosen threshold.", transform=ax1.transAxes, fontsize=8.5, color="#444444")

    ax2b = ax2.twinx()
    ax2.plot(df["threshold_cells"], df["total_length_m"], marker="o", color="#2c7fb8", lw=1.8, label="Total length (m)")
    ax2b.plot(df["threshold_cells"], df["segments"], marker="s", color="#7a0177", lw=1.5, label="Segments")
    ax2.axvline(5000, color="#222222", linestyle="--", lw=1.2)
    ax2.set_xlabel("Stream-accumulation threshold (cells)")
    ax2.set_ylabel("Total network length (m)", color="#2c7fb8")
    ax2b.set_ylabel("Segments", color="#7a0177")
    ax2.grid(True, axis="y", color="#dddddd", linewidth=0.7)
    ax2.tick_params(axis='y', labelcolor="#2c7fb8")
    ax2b.tick_params(axis='y', labelcolor="#7a0177")

    # Combined legend
    handles2, labels2 = ax2.get_legend_handles_labels()
    handles3, labels3 = ax2b.get_legend_handles_labels()
    ax2.legend(handles2 + handles3, labels2 + labels3, loc="upper right", frameon=True, fontsize=8)

    fig.text(0.5, 0.01, "The selected threshold balances network completeness against map legibility while preserving strong hazard overlap at the parcel scale.", ha="center", fontsize=9)
    fig.tight_layout(rect=[0.03, 0.04, 1, 0.97])
    save(fig, FIGDIR / "figure6_threshold_justification.png")


def main():
    fig1_context_overview()
    fig2_terrain_drainage()
    fig3_parcel_overlap()
    fig4_terrain_comparison()
    fig5_satellite_validation()
    fig6_threshold_justification()
    print(f"Wrote figures to {FIGDIR}")


if __name__ == "__main__":
    main()
