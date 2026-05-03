from __future__ import annotations

import argparse
from pathlib import Path

from whitebox.whitebox_tools import WhiteboxTools

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEM = ROOT / "data/raw/dem/borrego_valley_3dep_10m.tif"
DEFAULT_OUTDIR = ROOT / "data/processed/terrain"


def derive_terrain(dem_path: Path, outdir: Path) -> dict[str, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    dem_path = dem_path.resolve()
    outdir = outdir.resolve()
    wbt = WhiteboxTools()
    wbt.set_working_dir(str(outdir))

    stem = dem_path.stem
    filled = outdir / f"{stem}_filled.tif"
    slope = outdir / f"{stem}_slope_degrees.tif"
    d8 = outdir / f"{stem}_d8_flow_accum.tif"

    # Prototype conditioning: fill sinks so we can validate the terrain workflow.
    # Later phases can swap in breaching and sensitivity testing.
    wbt.fill_depressions(str(dem_path), str(filled), fix_flats=True)
    wbt.slope(str(filled), str(slope), units="degrees")
    wbt.d8_flow_accumulation(str(filled), str(d8), out_type="cells")

    return {"filled": filled, "slope": slope, "d8_accum": d8}


def main() -> None:
    parser = argparse.ArgumentParser(description="Derive initial terrain metrics from a prototype DEM.")
    parser.add_argument("--dem", type=Path, default=DEFAULT_DEM)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    args = parser.parse_args()

    outputs = derive_terrain(args.dem, args.outdir)
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
