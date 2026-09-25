"""Local-inertial solver against conservation laws and an analytic solution."""

import numpy as np
import pytest

from floodflow.hydraulics import Grid, SolverParams, State, advance, mass_balance, simulate

MM_H = 1e-3 / 3600  # mm/h → m/s


def test_closed_basin_conserves_mass_on_steep_terrain():
    """Steep random terrain, walls all round: every drop of rain is stored,
    depths never go negative (volume limiter), and the budget closes."""
    rng = np.random.default_rng(0)
    z = rng.uniform(0, 5, (30, 40)) + np.linspace(0, 20, 40)  # up to ~50% slopes
    grid = Grid(z, dx=1.0, manning_n=0.03, outlets=np.zeros(z.shape, bool))
    state = simulate(grid, np.full(4, 100 * MM_H), block_s=300, t_after=600,
                     log_every_s=1e9)
    mb = mass_balance(grid, state)
    assert state.h.min() >= 0.0
    assert mb["outflow_m3"] == 0.0
    assert mb["clipped_m3"] < 1e-9 * mb["rain_m3"]
    assert abs(mb["error_rel"]) < 1e-10
    assert mb["storage_m3"] == pytest.approx(mb["rain_m3"], rel=1e-10)


def test_lake_at_rest_stays_at_rest():
    """A flat water surface over a bumpy bed (with dry islands) must not move."""
    rng = np.random.default_rng(1)
    z = rng.uniform(0, 6, (25, 25))
    grid = Grid(z, dx=2.0, outlets=np.zeros(z.shape, bool))
    state = State.dry(grid.shape)
    state.h[:] = np.maximum(5.0 - z, 0.0)
    h0 = state.h.copy()
    advance(grid, state, SolverParams(), t_end=600.0)
    assert np.abs(state.qx).max() < 1e-12
    assert np.abs(state.qy).max() < 1e-12
    assert np.abs(state.h - h0).max() < 1e-12


def test_tilted_plane_matches_kinematic_steady_state():
    """Rain on a plane draining east: at steady state, outflow = rainfall and
    depth follows Manning normal depth for q(x) = i·x:
        h(x) = (n i x / √S)^(3/5)."""
    dx, nx, ny, S, n, i = 2.0, 100, 6, 0.01, 0.03, 50 * MM_H
    x_down = (np.arange(nx) + 1) * dx               # distance to each cell's east face
    z = np.tile(10.0 - S * (np.arange(nx) + 0.5) * dx, (ny, 1))
    outlets = np.zeros((4, ny, nx), bool)
    outlets[1, :, -1] = True                        # east side of the last column only
    grid = Grid(z, dx=dx, manning_n=n, outlets=outlets, s_out_min=S)
    state = simulate(grid, np.array([i]), block_s=3600, t_after=0,
                     params=SolverParams(manning_n=n), log_every_s=1e9)

    # Outflow rate at the east edge equals the rainfall rate on the plane
    q_out = state.qx[:, -1].mean()
    assert q_out == pytest.approx(i * nx * dx, rel=0.01)

    # Depth profile. On a downhill face the flow depth is the upstream cell's
    # depth, so cell k's depth carries the discharge at its east face.
    h_exact = (n * i * x_down / np.sqrt(S)) ** 0.6
    mid = slice(10, nx - 1)
    assert np.allclose(state.h[ny // 2, mid], h_exact[mid], rtol=0.01)
    assert abs(mass_balance(grid, state)["error_rel"]) < 1e-10


@pytest.mark.parametrize("S", [0.1, 0.3])
def test_steep_plane_rising_limb_matches_kinematic_wave(S):
    """On steep planes flow is supercritical. The outlet hydrograph must
    rise like the kinematic wave, q/q_e = (t/t_e)^(5/3), and settle at normal
    depth. A gravity-wave-only Δt went unstable here; a Froude cap of 1
    delayed the peak ~1.5× at S = 0.3."""
    dx, nx, ny, n, i = 2.0, 200, 3, 0.045, 100 * MM_H
    L = nx * dx
    z = np.tile(300.0 - S * (np.arange(nx) + 0.5) * dx, (ny, 1))
    outlets = np.zeros((4, ny, nx), bool)
    outlets[1, :, -1] = True
    grid = Grid(z, dx=dx, manning_n=n, outlets=outlets, s_out_min=S)
    t_e = (L * n / (np.sqrt(S) * i ** (2 / 3))) ** 0.6
    state, params = State.dry(grid.shape), SolverParams(manning_n=n)
    ts, qs = [], []
    for k in range(1, 81):
        advance(grid, state, params, t_end=k * t_e / 40, rain_rate=i)
        ts.append(state.t / t_e)
        qs.append(state.qx[1, -1] / (i * L))
    q = np.maximum.accumulate(qs)
    assert np.interp(0.5, q, ts) == pytest.approx(0.5 ** 0.6, abs=0.03)
    h_normal = (n * i * L / np.sqrt(S)) ** 0.6
    assert state.h[1, -1] == pytest.approx(h_normal, rel=0.03)
    v_normal = i * L / h_normal
    assert state.v_max.max() < 1.15 * v_normal
