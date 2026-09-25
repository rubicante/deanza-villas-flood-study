"""Run the 2D solver on Modal: `floodflow flood --remote`.

Modal starts a temporary machine for the call, runs `hydraulics.simulate`
there, returns the result, and shuts the machine down (billed per second).
The `floodflow` source is shipped but only `hydraulics` is imported there
(the package's exports are lazy), so the image needs just numpy and numba;
terrain, storm and summaries stay local.

Credentials: MODAL_TOKEN_ID and MODAL_TOKEN_SECRET, from the environment or
the repo's `.env` (only those two keys are read from it).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from floodflow.hydraulics import Grid, SolverParams, State

_REPO = Path(__file__).resolve().parents[1]
_TOKEN_KEYS = ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET")


def _load_tokens(env_file: Path = _REPO / ".env") -> None:
    if all(os.environ.get(k) for k in _TOKEN_KEYS) or not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        key, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and key.strip() in _TOKEN_KEYS:
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_tokens()

import modal  # noqa: E402  (reads the tokens at import)

DEFAULT_CPU = 64
app = modal.App("floodflow")
image = (
    modal.Image.debian_slim(python_version="3.13")
    .pip_install("numpy==2.4.4", "numba==0.65.1")
    .add_local_python_source("floodflow")
)
# Fields `summarise` and `mass_balance` read; qx/qy/il_left stay remote (≈3× the data).
_RETURNED = ("h", "h_max", "v_max", "dv_max", "t_hmax")


@app.function(image=image, cpu=DEFAULT_CPU, memory=16384, timeout=6 * 3600)
def _simulate(z: np.ndarray, dx: float, manning_n: float, rain_blocks: np.ndarray,
              block_s: float, t_after: float, params: dict, threads: int) -> dict:
    import numba

    from floodflow import hydraulics as hy
    numba.set_num_threads(min(threads, numba.config.NUMBA_NUM_THREADS))
    grid = hy.Grid(z, dx, manning_n=manning_n)
    st = hy.simulate(grid, rain_blocks, block_s, t_after, hy.SolverParams(**params))
    return {**{k: getattr(st, k) for k in _RETURNED},
            "t": st.t, "steps": st.steps, "budget": st.budget,
            "threads": numba.get_num_threads(), "cpu_count": os.cpu_count()}


def simulate(grid: Grid, rain_blocks: np.ndarray, block_s: float, t_after: float,
             params: SolverParams, z: np.ndarray, cpu: int = DEFAULT_CPU) -> State:
    """Same contract as `hydraulics.simulate`, run on a `cpu`-core Modal machine.
    `z` is the elevation `grid` was built from (the remote side rebuilds the grid).
    The returned State has no fluxes or initial-loss store (empty arrays)."""
    from dataclasses import asdict
    with modal.enable_output(), app.run():
        out = _simulate.with_options(cpu=cpu).remote(
            z, grid.dx, params.manning_n, rain_blocks, block_s, t_after, asdict(params), cpu)
    print(f"  remote: {cpu} cores requested, {out['threads']} numba threads, "
          f"os.cpu_count() = {out['cpu_count']}")
    empty = np.empty((0, 0))
    return State(qx=empty, qy=empty, il_left=empty, t=out["t"], steps=out["steps"],
                 budget=out["budget"], **{k: out[k] for k in _RETURNED})
