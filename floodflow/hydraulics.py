"""2D rain-on-grid hydraulics: a local-inertial shallow-water solver.

The scheme is the one used by LISFLOOD-FP (Bates et al. 2010) with the
θ-weighted flux of de Almeida et al. (2012). Water depth `h` lives at cell
centres, unit-width discharge `q` (m²/s) on cell faces:

    q ← [θ q + (1-θ)/2 (q_left + q_right) − g h_f Δt ∂η/∂x]
        / [1 + g Δt n² |q| / h_f^(7/3)]

where η = z + h and h_f = max(η) − max(z) across the face. Advection is
dropped (hence "local inertial"), which is accurate for the gradually varied,
friction-dominated flow of rain-on-grid runoff. Three safeguards keep it
stable on steep, mostly-dry terrain:

- Δt = cfl · dx / max over faces of (|q| / h_f + √(g h_f)), capped at
  `dt_max`. The usual local-inertial limit uses only the gravity-wave speed
  √(g h_max); on steep terrain the flow itself is faster than that
  (supercritical), and that Δt let canyon and sheet flow go unstable. The
  old workaround, a Froude cap of 1, made 30% slopes ~1.5× slower to peak
  with depths 55% too high; it's still available as `fr_max`.
- A volume limiter scales a cell's outflows so it never gives away more water
  than it holds. This makes depths non-negative and the scheme exactly
  mass-conservative (to round-off).

Cells outside `active` (or with NaN elevation) are off the grid. Faces between
an active cell and the outside are free outfalls: normal-depth outflow with
the bed slope extrapolated from the inner neighbour (at least `s_out_min`),
never inflow. `outlets` restricts which cells may discharge (others are walls):
shape (ny, nx), or (4, ny, nx) to choose per side (W, E, N, S).

Losses are initial-loss / continuing-loss: the first `initial_loss` metres of
rain on each cell are lost, then up to `loss_rate` m/s is removed from ponded
water (so run-on infiltrates too, as on a desert fan).

Sign convention: +x is east (increasing column), +y is south (increasing row).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from numba import njit, prange

G = 9.81


@dataclass(frozen=True)
class SolverParams:
    manning_n: float = 0.045
    theta: float = 0.8           # de Almeida weighting; 1 = Bates 2010
    cfl: float = 0.3             # on the flow-speed Δt; 0.5 overshoots on 30–60% planes
    dt_max: float = 2.0          # s
    fr_max: float = float("inf")  # optional Froude cap on face flux (1 = LISFLOOD-FP style)
    h_dry: float = 1e-4          # m; faces shallower than this carry no flow
    h_speed: float = 1e-3        # m; cells shallower than this don't set Δt
    h_track: float = 0.01        # m; speeds only recorded above this depth
    s_out_min: float = 1e-3      # minimum outfall slope
    initial_loss: float = 0.0    # m
    loss_rate: float = 0.0       # m/s


@dataclass
class State:
    """Everything that evolves, plus the running maxima and a mass budget."""
    h: np.ndarray
    qx: np.ndarray               # (ny, nx+1)
    qy: np.ndarray               # (ny+1, nx)
    il_left: np.ndarray          # initial loss still to be satisfied (m)
    h_max: np.ndarray
    v_max: np.ndarray
    dv_max: np.ndarray           # depth × speed (m²/s)
    t_hmax: np.ndarray           # s
    t: float = 0.0
    steps: int = 0
    budget: dict = field(default_factory=lambda: {
        "rain_m3": 0.0, "loss_m3": 0.0, "outflow_m3": 0.0, "clipped_m3": 0.0})

    @classmethod
    def dry(cls, shape: tuple[int, int], initial_loss: float = 0.0) -> State:
        ny, nx = shape
        return cls(
            h=np.zeros(shape), qx=np.zeros((ny, nx + 1)), qy=np.zeros((ny + 1, nx)),
            il_left=np.full(shape, initial_loss), h_max=np.zeros(shape),
            v_max=np.zeros(shape), dv_max=np.zeros(shape), t_hmax=np.zeros(shape))


class Grid:
    """Elevation, active mask, Manning's n², and per-cell outfall slopes."""

    def __init__(self, z: np.ndarray, dx: float, active: np.ndarray | None = None,
                 manning_n: float | np.ndarray = 0.045, s_out_min: float = 1e-3,
                 outlets: np.ndarray | None = None):
        z = np.asarray(z, dtype=np.float64)
        act = np.isfinite(z)
        if active is not None:
            act &= np.asarray(active, dtype=bool)
        self.z = np.where(act, z, 0.0)
        self.active = act.astype(np.uint8)
        self.dx = float(dx)
        n = np.broadcast_to(np.asarray(manning_n, dtype=np.float64), z.shape)
        self.n2 = np.ascontiguousarray(n * n)
        self.s_out = _outfall_slopes(self.z, self.active, self.dx, s_out_min)
        if outlets is not None:
            closed = ~np.broadcast_to(np.asarray(outlets, dtype=bool), self.s_out.shape)
            self.s_out[closed] = 0.0  # zero slope = wall
        self.n_active = int(act.sum())

    @property
    def shape(self) -> tuple[int, int]:
        return self.z.shape


def _outfall_slopes(z, active, dx, s_min):
    """(4, ny, nx) outward bed slope for each side (W, E, N, S), extrapolated
    from the opposite neighbour; only used where that side is off-grid."""
    ny, nx = z.shape
    s = np.full((4, ny, nx), s_min)
    act = active.astype(bool)
    # West side: terrain falling westward ⇔ z[c+1] > z[c]
    inner = act[:, :-1] & act[:, 1:]
    s[0, :, :-1] = np.where(inner, (z[:, 1:] - z[:, :-1]) / dx, s_min)
    s[1, :, 1:] = np.where(inner, (z[:, :-1] - z[:, 1:]) / dx, s_min)
    inner = act[:-1, :] & act[1:, :]
    s[2, :-1, :] = np.where(inner, (z[1:, :] - z[:-1, :]) / dx, s_min)
    s[3, 1:, :] = np.where(inner, (z[:-1, :] - z[1:, :]) / dx, s_min)
    return np.ascontiguousarray(np.maximum(s, s_min))


# -- Kernels --

@njit(inline="always")
def _face_flux(q0, q_l, q_r, eta_a, eta_b, z_a, z_b, n2, dt, dx, theta, fr_max, h_dry):
    """Local-inertial flux from cell a to cell b (positive = a → b)."""
    hf = max(eta_a, eta_b) - max(z_a, z_b)
    if hf <= h_dry:
        return 0.0
    slope = (eta_b - eta_a) / dx
    qa = theta * q0 + 0.5 * (1.0 - theta) * (q_l + q_r)
    q = (qa - G * hf * dt * slope) / (1.0 + G * dt * n2 * abs(q0) / hf ** (7.0 / 3.0))
    qcap = fr_max * hf * np.sqrt(G * hf)
    if q > qcap:
        q = qcap
    elif q < -qcap:
        q = -qcap
    return q


@njit(inline="always")
def _outfall(h, s_out, n2, fr_max, h_dry):
    """Normal-depth outflow (m²/s, ≥ 0) through an off-grid face."""
    if h <= h_dry:
        return 0.0
    q = h ** (5.0 / 3.0) * np.sqrt(s_out / n2)
    qcap = fr_max * h * np.sqrt(G * h)
    return min(q, qcap)


@njit(parallel=True, cache=True)
def _fluxes_x(z, h, active, n2, s_out, qx, qx_new, dt, dx, theta, fr_max, h_dry):
    ny, nx = h.shape
    for r in prange(ny):
        for f in range(nx + 1):
            a = f - 1
            b = f
            a_on = a >= 0 and active[r, a] == 1
            b_on = b < nx and active[r, b] == 1
            if a_on and b_on:
                q_l = qx[r, f - 1] if f - 1 >= 0 else qx[r, f]
                q_r = qx[r, f + 1] if f + 1 <= nx else qx[r, f]
                n2f = 0.5 * (n2[r, a] + n2[r, b])
                qx_new[r, f] = _face_flux(qx[r, f], q_l, q_r,
                                          z[r, a] + h[r, a], z[r, b] + h[r, b],
                                          z[r, a], z[r, b], n2f, dt, dx, theta, fr_max, h_dry)
            elif a_on:     # east side of a is off-grid
                qx_new[r, f] = _outfall(h[r, a], s_out[1, r, a], n2[r, a], fr_max, h_dry)
            elif b_on:     # west side of b is off-grid
                qx_new[r, f] = -_outfall(h[r, b], s_out[0, r, b], n2[r, b], fr_max, h_dry)
            else:
                qx_new[r, f] = 0.0


@njit(parallel=True, cache=True)
def _fluxes_y(z, h, active, n2, s_out, qy, qy_new, dt, dx, theta, fr_max, h_dry):
    ny, nx = h.shape
    for f in prange(ny + 1):
        a = f - 1
        b = f
        for c in range(nx):
            a_on = a >= 0 and active[a, c] == 1
            b_on = b < ny and active[b, c] == 1
            if a_on and b_on:
                q_l = qy[f - 1, c] if f - 1 >= 0 else qy[f, c]
                q_r = qy[f + 1, c] if f + 1 <= ny else qy[f, c]
                n2f = 0.5 * (n2[a, c] + n2[b, c])
                qy_new[f, c] = _face_flux(qy[f, c], q_l, q_r,
                                          z[a, c] + h[a, c], z[b, c] + h[b, c],
                                          z[a, c], z[b, c], n2f, dt, dx, theta, fr_max, h_dry)
            elif a_on:     # south side of a is off-grid
                qy_new[f, c] = _outfall(h[a, c], s_out[3, a, c], n2[a, c], fr_max, h_dry)
            elif b_on:     # north side of b is off-grid
                qy_new[f, c] = -_outfall(h[b, c], s_out[2, b, c], n2[b, c], fr_max, h_dry)
            else:
                qy_new[f, c] = 0.0


@njit(parallel=True, cache=True)
def _limit(h, rain_eff, active, qx, qy, scale, dt, dx):
    """Scale each cell's outflows so it can't give away more than it holds."""
    ny, nx = h.shape
    for r in prange(ny):
        for c in range(nx):
            if active[r, c] == 0:
                scale[r, c] = 1.0
                continue
            out = (max(qx[r, c + 1], 0.0) + max(-qx[r, c], 0.0)
                   + max(qy[r + 1, c], 0.0) + max(-qy[r, c], 0.0)) * dt / dx
            avail = h[r, c] + rain_eff[r, c]
            scale[r, c] = avail / out if out > avail else 1.0
    for r in prange(ny):
        for f in range(nx + 1):
            q = qx[r, f]
            if q > 0.0 and f - 1 >= 0:
                qx[r, f] = q * scale[r, f - 1]
            elif q < 0.0 and f < nx:
                qx[r, f] = q * scale[r, f]
    for f in prange(ny + 1):
        for c in range(nx):
            q = qy[f, c]
            if q > 0.0 and f - 1 >= 0:
                qy[f, c] = q * scale[f - 1, c]
            elif q < 0.0 and f < ny:
                qy[f, c] = q * scale[f, c]


@njit(parallel=True, cache=True)
def _rain(active, il_left, rain_eff, depth):
    """Split this step's rain `depth` into initial loss and effective rain.
    Returns the volume-per-area lost (sum over cells, m)."""
    ny, nx = active.shape
    lost = 0.0
    for r in prange(ny):
        for c in range(nx):
            if active[r, c] == 0:
                rain_eff[r, c] = 0.0
                continue
            take = min(il_left[r, c], depth)
            il_left[r, c] -= take
            rain_eff[r, c] = depth - take
            lost += take
    return lost


@njit(parallel=True, cache=True)
def _update(h, rain_eff, active, qx, qy, dt, dx, loss_dt, t, h_max, t_hmax):
    """Continuity + continuing loss + running max depth.
    Returns (outflow m, continuing loss m, clipped m), each summed over cells."""
    ny, nx = h.shape
    out_sum = 0.0
    loss_sum = 0.0
    clip_sum = 0.0
    for r in prange(ny):
        for c in range(nx):
            if active[r, c] == 0:
                continue
            qw = qx[r, c]
            qe = qx[r, c + 1]
            qn = qy[r, c]
            qs = qy[r + 1, c]
            hn = h[r, c] + rain_eff[r, c] + (qw - qe + qn - qs) * dt / dx
            # Boundary outflow through off-grid faces
            if c == 0 or active[r, c - 1] == 0:
                out_sum += max(-qw, 0.0) * dt / dx
            if c == nx - 1 or active[r, c + 1] == 0:
                out_sum += max(qe, 0.0) * dt / dx
            if r == 0 or active[r - 1, c] == 0:
                out_sum += max(-qn, 0.0) * dt / dx
            if r == ny - 1 or active[r + 1, c] == 0:
                out_sum += max(qs, 0.0) * dt / dx
            if hn < 0.0:
                clip_sum -= hn
                hn = 0.0
            if loss_dt > 0.0:
                take = min(hn, loss_dt)
                hn -= take
                loss_sum += take
            h[r, c] = hn
            if hn > h_max[r, c]:
                h_max[r, c] = hn
                t_hmax[r, c] = t
    return out_sum, loss_sum, clip_sum


@njit(inline="always")
def _face_depth(z, h, active, r, c, r2, c2):
    """Flow depth on the face between (r, c) and (r2, c2); the cell's own
    depth when the neighbour is off-grid (an outfall)."""
    ny, nx = h.shape
    if r2 < 0 or r2 >= ny or c2 < 0 or c2 >= nx or active[r2, c2] == 0:
        return h[r, c]
    return max(max(z[r, c] + h[r, c], z[r2, c2] + h[r2, c2]) - max(z[r, c], z[r2, c2]), 0.0)


@njit(parallel=True, cache=True)
def _track_speed(z, h, active, qx, qy, h_track, v_max, dv_max):
    """Running max speed and depth × speed. Velocity is face discharge over
    face flow depth (the speed the scheme moves water at), weighted by depth;
    dividing by the cell's own depth gave 100+ m/s where a channel spills
    onto a thin film. Call it with the depths the fluxes were computed from
    (before `_update`): after the update, a face the step's flux just drained
    reads e.g. 0.09 m²/s over 0.9 mm = 100 m/s."""
    ny, nx = h.shape
    for r in prange(ny):
        for c in range(nx):
            hc = h[r, c]
            if active[r, c] == 0 or hc <= h_track:
                continue
            hw = _face_depth(z, h, active, r, c, r, c - 1)
            he = _face_depth(z, h, active, r, c, r, c + 1)
            hn = _face_depth(z, h, active, r, c, r - 1, c)
            hs = _face_depth(z, h, active, r, c, r + 1, c)
            ux = (qx[r, c] + qx[r, c + 1]) / (hw + he) if hw + he > 0.0 else 0.0
            uy = (qy[r, c] + qy[r + 1, c]) / (hn + hs) if hn + hs > 0.0 else 0.0
            v = np.sqrt(ux * ux + uy * uy)
            if v > v_max[r, c]:
                v_max[r, c] = v
            if v * hc > dv_max[r, c]:
                dv_max[r, c] = v * hc


@njit(parallel=True, cache=True)
def _signal_speed_max(z, h, qx, qy, active, h_min):
    """max over faces of |q| / h_f + √(g h_f), the speed the flux update
    actually moves water at. Face-based on purpose: dividing a face flux by
    the receiving cell's depth (a deep channel spilling onto a 1 mm film)
    gives spurious 100 m/s speeds that collapse Δt. Faces shallower than
    `h_min` are skipped."""
    ny, nx = h.shape
    m = 0.0
    for r in prange(ny):
        for c in range(nx):
            if active[r, c] == 0:
                continue
            eta = z[r, c] + h[r, c]
            if c + 1 < nx and active[r, c + 1] == 1:
                hf = max(eta, z[r, c + 1] + h[r, c + 1]) - max(z[r, c], z[r, c + 1])
                if hf > h_min:
                    m = max(m, abs(qx[r, c + 1]) / hf + np.sqrt(G * hf))
            if r + 1 < ny and active[r + 1, c] == 1:
                hf = max(eta, z[r + 1, c] + h[r + 1, c]) - max(z[r, c], z[r + 1, c])
                if hf > h_min:
                    m = max(m, abs(qy[r + 1, c]) / hf + np.sqrt(G * hf))
            if h[r, c] > h_min:     # outfalls and anything else: gravity wave
                m = max(m, np.sqrt(G * h[r, c]))
    return m


# -- Driver --

def advance(grid: Grid, state: State, params: SolverParams, t_end: float,
            rain_rate: float = 0.0) -> None:
    """Advance `state` to `t_end` (s) under uniform `rain_rate` (m/s)."""
    p = params
    dx = grid.dx
    cell_area = dx * dx
    qx_new = np.empty_like(state.qx)
    qy_new = np.empty_like(state.qy)
    scale = np.empty_like(state.h)
    rain_eff = np.zeros_like(state.h)
    b = state.budget
    while state.t < t_end - 1e-9:
        speed = _signal_speed_max(grid.z, state.h, state.qx, state.qy, grid.active, p.h_speed)
        dt = p.dt_max if speed == 0.0 else min(p.dt_max, p.cfl * dx / speed)
        dt = min(dt, t_end - state.t)
        if rain_rate > 0.0:
            il = _rain(grid.active, state.il_left, rain_eff, rain_rate * dt)
            b["rain_m3"] += rain_rate * dt * grid.n_active * cell_area
            b["loss_m3"] += il * cell_area
        else:
            rain_eff[:] = 0.0
        _fluxes_x(grid.z, state.h, grid.active, grid.n2, grid.s_out, state.qx, qx_new,
                  dt, dx, p.theta, p.fr_max, p.h_dry)
        _fluxes_y(grid.z, state.h, grid.active, grid.n2, grid.s_out, state.qy, qy_new,
                  dt, dx, p.theta, p.fr_max, p.h_dry)
        state.qx, qx_new = qx_new, state.qx
        state.qy, qy_new = qy_new, state.qy
        _limit(state.h, rain_eff, grid.active, state.qx, state.qy, scale, dt, dx)
        # Before `_update`: the fluxes were computed from these depths.
        _track_speed(grid.z, state.h, grid.active, state.qx, state.qy, p.h_track,
                     state.v_max, state.dv_max)
        state.t += dt
        state.steps += 1
        out, loss, clip = _update(state.h, rain_eff, grid.active, state.qx, state.qy,
                                  dt, dx, p.loss_rate * dt, state.t, state.h_max, state.t_hmax)
        b["outflow_m3"] += out * cell_area
        b["loss_m3"] += loss * cell_area
        b["clipped_m3"] += clip * cell_area


def mass_balance(grid: Grid, state: State) -> dict:
    """Budget terms (m³) and the relative closure error."""
    b = dict(state.budget)
    b["storage_m3"] = float(state.h[grid.active == 1].sum() * grid.dx ** 2)
    resid = (b["rain_m3"] + b["clipped_m3"]
             - b["loss_m3"] - b["outflow_m3"] - b["storage_m3"])
    b["error_m3"] = resid
    b["error_rel"] = resid / b["rain_m3"] if b["rain_m3"] > 0 else 0.0
    return b


def simulate(grid: Grid, rain_blocks: np.ndarray, block_s: float, t_after: float,
             params: SolverParams = SolverParams(), log_every_s: float = 600.0) -> State:
    """Run a hyetograph (`rain_blocks` in m/s, each `block_s` long) and then
    `t_after` seconds of recession. Returns the final State (with maxima)."""
    state = State.dry(grid.shape, params.initial_loss)
    segments = [(i * block_s, (i + 1) * block_s, float(r)) for i, r in enumerate(rain_blocks)]
    t_rain_end = len(rain_blocks) * block_s
    if t_after > 0:
        segments.append((t_rain_end, t_rain_end + t_after, 0.0))
    t0 = time.time()
    next_log = log_every_s
    for _, seg_end, rate in segments:
        while state.t < seg_end - 1e-9:
            advance(grid, state, params, min(seg_end, next_log), rain_rate=rate)
            if state.t >= next_log - 1e-9 or state.t >= segments[-1][1] - 1e-9:
                next_log += log_every_s
                mb = mass_balance(grid, state)
                print(f"  t={state.t / 60:6.1f} min  steps={state.steps:7d}  "
                      f"h_max={state.h.max():6.3f} m  storage={mb['storage_m3']:9.0f} m³  "
                      f"out={mb['outflow_m3']:9.0f} m³  err={mb['error_rel']:+.1e}  "
                      f"({time.time() - t0:.0f}s)", flush=True)
    return state
