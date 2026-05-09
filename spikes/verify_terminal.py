"""Check terminal rate: stream cells whose downstream neighbor is not also a stream cell."""
import numpy as np
import rasterio

streams_f = "/home/hermes/workspace/deanza-villas-flood-study/data/derived/henderson/streams_d8_1m_250.tif"
ptr_f = "/home/hermes/workspace/deanza-villas-flood-study/data/derived/henderson/d8_pointer_1m.tif"

D8 = {1:(-1,1),2:(0,1),4:(1,1),8:(1,0),16:(1,-1),32:(0,-1),64:(-1,-1),128:(-1,0)}

with rasterio.open(streams_f) as src:
    streams = src.read(1)
    s_shape = src.shape
with rasterio.open(ptr_f) as src:
    ptr = src.read(1)

stream_cells = np.argwhere(streams > 0)
n_stream = len(stream_cells)

terminal = 0
oob = 0
pits = 0
for r, c in stream_cells:
    p = int(ptr[r,c])
    if p == 0 or p not in D8:
        pits += 1
        continue
    dr, dc = D8[p]
    nr, nc = r+dr, c+dc
    if nr < 0 or nr >= s_shape[0] or nc < 0 or nc >= s_shape[1]:
        oob += 1
        continue
    if streams[nr,nc] == 0:
        terminal += 1

print(f"Stream cells: {n_stream:,}")
print(f"Terminal: {terminal:,} ({terminal/n_stream*100:.2f}%)")
print(f"Out of bounds: {oob:,}")
print(f"Null ptr: {pits:,}")
