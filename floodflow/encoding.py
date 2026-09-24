"""Flow-direction encodings shared by the pipeline, verification and
experimental reachability code. One copy, so a table fix lands everywhere.

Rows increase southward (raster order); (dr, dc) are row/col deltas.
"""

import numpy as np

# ── D8 encoding (WBT: 1=NE,2=E,4=SE,8=S,16=SW,32=W,64=NW,128=N) ──

# dr, dc for each D8 code
D8_DELTA: dict[int, tuple[int, int]] = {
    1: (-1, 1),     # NE
    2: (0, 1),      # E
    4: (1, 1),      # SE
    8: (1, 0),      # S
    16: (1, -1),    # SW
    32: (0, -1),    # W
    64: (-1, -1),   # NW
    128: (-1, 0),   # N
}


# ── D∞ encoding (WBT: angle in degrees, 0=North, clockwise) ──

# Neighbor (dr, dc) for each of the 8 direction indices, 0=N, 1=NE, 2=E, ...
DINF_NEIGHBORS: list[tuple[int, int]] = [
    (-1, 0),   # 0: N
    (-1, 1),   # 1: NE
    (0, 1),    # 2: E
    (1, 1),    # 3: SE
    (1, 0),    # 4: S
    (1, -1),   # 5: SW
    (0, -1),   # 6: W
    (-1, -1),  # 7: NW
]


def dinf_neighbors(angle_deg: float,
                    with_proportions: bool = False,
                    ) -> list[tuple]:
    """Return list of (dr, dc) [and optionally proportion] this D∞ angle flows toward.

    If with_proportions=True, returns list of (dr, dc, proportion) where
    proportions sum to 1.0.  Neighbor 1 gets (1-frac), neighbor 2 gets frac.
    Cardinal/ordinal angles (exact multiples of 45°) have only one neighbor
    with proportion 1.0.

    Boolean reachability: return both neighbors unless one gets zero flow
    (angle exactly aligned with a cardinal/ordinal direction)."""
    if angle_deg < 0 or angle_deg > 360:
        return []
    angle_deg %= 360  # normalize 360.0 and any float drift to [0, 360)

    idx1 = int(angle_deg // 45) % 8
    frac = (angle_deg - idx1 * 45) / 45.0
    idx2 = (idx1 + 1) % 8

    neighbors = []
    if frac < 1 - 1e-6:  # non-zero flow to neighbor idx1
        item = DINF_NEIGHBORS[idx1]
        neighbors.append((*item, 1.0 - frac) if with_proportions else item)
    if frac > 1e-6:  # non-zero flow to neighbor idx2
        item = DINF_NEIGHBORS[idx2]
        neighbors.append((*item, frac) if with_proportions else item)
    # If exactly 0 or exactly 45 etc., only one neighbor
    if not neighbors:
        item = DINF_NEIGHBORS[idx1]
        neighbors.append((*item, 1.0) if with_proportions else item)
    return neighbors


# WBT → pyflwdir D8 encoding translation (powers-of-2 LUT)
# WBT:     1=NE, 2=E, 4=SE, 8=S, 16=SW, 32=W, 64=NW, 128=N  (clockwise from NE)
# pyflwdir: 1=E, 2=SE, 4=S, 8=SW, 16=W, 32=NW, 64=N, 128=NE (clockwise from E)
WBT_TO_PYFLWDIR = np.zeros(256, dtype="uint8")
WBT_TO_PYFLWDIR[1] = 128   # NE → NE
WBT_TO_PYFLWDIR[2] = 1     # E  → E
WBT_TO_PYFLWDIR[4] = 2     # SE → SE
WBT_TO_PYFLWDIR[8] = 4     # S  → S
WBT_TO_PYFLWDIR[16] = 8    # SW → SW
WBT_TO_PYFLWDIR[32] = 16   # W  → W
WBT_TO_PYFLWDIR[64] = 32   # NW → NW
WBT_TO_PYFLWDIR[128] = 64  # N  → N
