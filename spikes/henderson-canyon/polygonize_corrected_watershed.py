"""Polygonize corrected BFS watershed mask to GeoJSON boundary."""
import numpy as np
from pathlib import Path
import rasterio
from rasterio import features
from shapely.geometry import shape
from shapely.ops import unary_union
import geopandas as gpd

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")
SPIKE = ROOT / "spikes" / "henderson-canyon"

# Load BFS mask
with rasterio.open(SPIKE / "actual_watershed_bfs.tif") as src:
    mask = src.read(1) > 0
    crs = src.crs
    transform = src.transform
    resolution = abs(transform.a)

cells = mask.sum()
area_km2 = cells * resolution * resolution / 1e6
print(f"BFS watershed: {cells:,} cells, {area_km2:.1f} km² at {resolution:.1f}m")

# Polygonize
print("Polygonizing...")
binary = mask.astype("int16")
results = list(features.shapes(binary, mask=mask.astype("uint8"), transform=transform))

geoms = [shape(g) for g, v in results if v == 1]
print(f"  {len(geoms)} individual polygons")

merged = unary_union(geoms)
simplified = merged.simplify(10, preserve_topology=True)
print(f"  Merged: {merged.geom_type}, area: {merged.area/1e6:.1f} km²")
print(f"  Simplified: {len(simplified.exterior.coords) if hasattr(simplified, 'exterior') else 'multi'} vertices")

# Reproject to WGS84 and save
gdf_5070 = gpd.GeoDataFrame(
    [{"name": "Henderson Canyon contributing watershed (corrected)",
      "source": "BFS upstream trace from D8 pointer + De Anza community pour points",
      "area_km2": round(area_km2, 2),
      "cells": int(cells),
      "resolution_m": resolution,
      "note": "Corrected 2026-05-05. WBT watershed() produced a 107 km² false-positive result (96% of cells don't drain to community). This BFS trace is the actual D8 upstream contributing area."}],
    geometry=[simplified],
    crs=crs
)

gdf_4326 = gdf_5070.to_crs("EPSG:4326")

out_path = ROOT / "data/vectors/henderson_watershed_boundary.geojson"
backup_path = ROOT / "data/vectors/henderson_watershed_boundary_WRONG_107km2.geojson"

# Back up the old (wrong) one
old = gpd.read_file(out_path)
old.to_file(backup_path, driver="GeoJSON")
print(f"Backed up old boundary: {backup_path}")

# Save corrected
gdf_4326.to_file(out_path, driver="GeoJSON")
print(f"Saved corrected boundary: {out_path}")

# Print extent
bounds = gdf_4326.total_bounds
print(f"\nCorrected WGS84 extent: lon [{bounds[0]:.4f}, {bounds[2]:.4f}], lat [{bounds[1]:.4f}, {bounds[3]:.4f}]")
print(f"E-W: {(bounds[2]-bounds[0])*111.32*0.85:.1f} km")
print(f"N-S: {(bounds[3]-bounds[1])*111.32:.1f} km")

# Also save EPSG:5070 version for the validation map
gdf_5070_out = ROOT / "data/vectors/henderson_watershed_boundary_5070.geojson"
gdf_5070.to_file(gdf_5070_out, driver="GeoJSON")
print(f"Saved EPSG:5070 version: {gdf_5070_out}")
