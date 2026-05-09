"""Check D∞ terminal rate."""
import numpy as np
import rasterio

STREAMS = "/home/hermes/workspace/deanza-villas-flood-study/data/derived/henderson/streams_dinf_1m_250.tif"
PTR = "/home/hermes/workspace/deanza-villas-flood-study/data/derived/henderson/dinf_pointer_1m.tif"

with rasterio.open(STREAMS) as src:
    streams = src.read(1)
    shape = src.shape
with rasterio.open(PTR) as src:
    ptr = src.read(1)

# D∞ neighbors (matching deliverable/reachability.py)
NEIGHBORS = [(0,1), (-1,1), (-1,0), (-1,-1), (0,-1), (1,-1), (1,0), (1,1)]

stream_cells = np.argwhere(streams > 0)
n_stream = len(stream_cells)

terminal = 0
pits = 0
oob = 0
for r, c in stream_cells:
    angle = float(ptr[r, c])
    if angle < 0 or angle > 360:
        pits += 1
        continue
    idx1 = int(angle // 45) % 8
    frac = (angle - idx1 * 45) / 45.0
    # Check if either neighbor is also a stream
    found = False
    for idx in [idx1, (idx1+1)%8]:
        if idx == idx1 and frac >= 1 - 1e-6:
            continue
        if idx != idx1 and frac <= 1e-6:
            continue
        dr, dc = NEIGHBORS[idx]
        nr, nc = r+dr, c+dc
        if nr < 0 or nr >= shape[0] or nc < 0 or nc >= shape[1]:
            oob += 1
            continue
        if streams[nr, nc] > 0:
            found = True
            break
    if not found:
        terminal += 1

print(f"D∞ stream cells: {n_stream:,}")
print(f"Terminal (no downstream stream): {terminal:,} ({terminal/n_stream*100:.2f}%)")
print(f"Null pointer: {pits:,}")
print(f"Out of bounds: {oob:,}")
