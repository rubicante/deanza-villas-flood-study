from __future__ import annotations

from pathlib import Path

from whitebox.whitebox_tools import WhiteboxTools

from scripts.study_config import config_path

DEM_PATH = config_path("paths", "dem_source_1m")
OUTDIR = config_path("paths", "terrain_outdir")


def derive_terrain() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    dem_path = DEM_PATH.resolve()
    outdir = OUTDIR.resolve()
    wbt = WhiteboxTools()
    wbt.set_working_dir(str(outdir))

    stem = dem_path.stem  # deanza_villas_2km_1m_dem

    # Breach-first-then-fill: preserves flow continuity across fan surfaces.
    # Simple fill alone creates artificial flat areas that block D8 routing.
    breached = outdir / f"{stem}_breached.tif"
    filled = outdir / f"{stem}_filled.tif"
    slope = outdir / f"{stem}_slope_degrees.tif"
    d8_accum = outdir / f"{stem}_d8_flow_accum.tif"
    d8_ptr = outdir / f"{stem}_d8_pointer.tif"
    dinf_accum = outdir / f"{stem}_dinf_flow_accum.tif"
    dinf_ptr = outdir / f"{stem}_dinf_pointer.tif"

    wbt.breach_depressions(str(dem_path), str(breached), max_length=250)
    wbt.fill_depressions(str(breached), str(filled), fix_flats=True)

    wbt.slope(str(filled), str(slope), units="degrees")

    wbt.d8_flow_accumulation(str(filled), str(d8_accum), out_type="cells")
    wbt.d8_pointer(str(filled), str(d8_ptr))

    # D-infinity: multi-direction flow accumulation (Tarboton 1997).
    # Divergence between D8 and D-infinity on fan surfaces is direct
    # evidence of sheet-flow/alluvial fan behavior.
    wbt.d_inf_flow_accumulation(str(filled), str(dinf_accum), out_type="cells")
    wbt.d_inf_pointer(str(filled), str(dinf_ptr))

    print(f"breached: {breached}")
    print(f"filled:   {filled}")
    print(f"slope:    {slope}")
    print(f"d8_accum: {d8_accum}")
    print(f"d8_ptr:   {d8_ptr}")
    print(f"dinf_acc: {dinf_accum}")
    print(f"dinf_ptr: {dinf_ptr}")


if __name__ == "__main__":
    derive_terrain()
