import numpy as np
import rasterio

acc_f = "/home/hermes/workspace/deanza-villas-flood-study/data/derived/henderson/d8_flow_accum_1m.tif"
ptr_f = "/home/hermes/workspace/deanza-villas-flood-study/data/derived/henderson/d8_pointer_1m.tif"

D8 = {1:(-1,1),2:(0,1),4:(1,1),8:(1,0),16:(1,-1),32:(0,-1),64:(-1,-1),128:(-1,0)}

with rasterio.open(acc_f) as src:
    acc = src.read(1)
    shp = src.shape
with rasterio.open(ptr_f) as src:
    ptr = src.read(1)

np.random.seed(42)
mask = ptr > 0
mask = mask & (ptr != -32768)
nonzero = np.argwhere(mask)
n = min(1000, len(nonzero))
idxs = np.random.choice(len(nonzero), n, replace=False)
samples = nonzero[idxs]

violations = 0
oob = 0
pits = 0
for r, c in samples:
    p = int(ptr[r,c])
    if p == 0 or p not in D8:
        pits += 1
        continue
    dr, dc = D8[p]
    nr, nc = r+dr, c+dc
    if nr < 0 or nr >= shp[0] or nc < 0 or nc >= shp[1]:
        oob += 1
        continue
    if acc[r,c] > acc[nr,nc]:
        violations += 1

print(f"Sampled {n} cells")
print(f"Monotonicity violations: {violations}")
print(f"Out of bounds: {oob}")
print(f"Pits (null ptr): {pits}")
print(f"Passed: {n - violations - oob - pits}")
print(f"Accum max: {acc.max():.0f}")
print(f"Accum shape: {shp}")
print(f"Watershed cells (accum>0): {(acc>0).sum():,}")
