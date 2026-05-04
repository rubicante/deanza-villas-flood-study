from __future__ import annotations

from whitebox.whitebox_tools import WhiteboxTools

from scripts.study_config import config_path

DEM_PATH = config_path("paths", "dem_source_output")
OUTDIR = config_path("paths", "terrain_outdir")


def derive_terrain() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    dem_path = DEM_PATH.resolve()
    outdir = OUTDIR.resolve()
    wbt = WhiteboxTools()
    wbt.set_working_dir(str(outdir))

    stem = dem_path.stem
    filled = outdir / f"{stem}_filled.tif"
    slope = outdir / f"{stem}_slope_degrees.tif"
    d8 = outdir / f"{stem}_d8_flow_accum.tif"

    # Prototype conditioning: fill sinks so we can validate the terrain workflow.
    # Later steps can swap in breaching and sensitivity testing.
    wbt.fill_depressions(str(dem_path), str(filled), fix_flats=True)
    wbt.slope(str(filled), str(slope), units="degrees")
    wbt.d8_flow_accumulation(str(filled), str(d8), out_type="cells")

    print(f"filled: {filled}")
    print(f"slope: {slope}")
    print(f"d8_accum: {d8}")


if __name__ == "__main__":
    derive_terrain()
