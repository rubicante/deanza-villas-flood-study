"""Compare D8 and D∞ reachable cells."""
import rasterio, numpy as np

d8_r = '/home/hermes/workspace/deanza-villas-flood-study/data/derived/henderson/streams_d8_1m_250_reachable.tif'
dinf_r = '/home/hermes/workspace/deanza-villas-flood-study/data/derived/henderson/streams_dinf_1m_250_reachable.tif'
d8_s = '/home/hermes/workspace/deanza-villas-flood-study/data/derived/henderson/streams_d8_1m_250.tif'
dinf_s = '/home/hermes/workspace/deanza-villas-flood-study/data/derived/henderson/streams_dinf_1m_250.tif'

with rasterio.open(d8_s) as s: d8 = s.read(1)
with rasterio.open(dinf_s) as s: dinf = s.read(1)
with rasterio.open(d8_r) as s: d8r = s.read(1)
with rasterio.open(dinf_r) as s: dinfr = s.read(1)

n_d8 = (d8>0).sum()
n_dinf = (dinf>0).sum()
n_d8r = (d8r>0).sum()
n_dinfr = (dinfr>0).sum()
print(f'D8 streams: {n_d8:,}, reachable: {n_d8r:,} ({n_d8r/n_d8*100:.1f}%)')
print(f'D∞ streams: {n_dinf:,}, reachable: {n_dinfr:,} ({n_dinfr/n_dinf*100:.1f}%)')

d8_set = set(zip(*np.where(d8r>0)))
dinf_set = set(zip(*np.where(dinfr>0)))
overlap = len(d8_set.intersection(dinf_set))
print(f'Overlap: {overlap:,}')
print(f'D8 only: {len(d8_set - dinf_set):,}')
print(f'D∞ only: {len(dinf_set - d8_set):,}')

# How many D8 reachable cells are on D∞ streams?
d8r_on_dinf = sum(1 for r,c in d8_set if dinf[r,c] > 0)
print(f'D8 reachable cells that are D∞ streams: {d8r_on_dinf:,} ({d8r_on_dinf/n_d8r*100:.1f}%)')

# How many D∞ reachable cells are on D8 streams?
dinfr_on_d8 = sum(1 for r,c in dinf_set if d8[r,c] > 0)
print(f'D∞ reachable cells that are D8 streams: {dinfr_on_d8:,} ({dinfr_on_d8/n_dinfr*100:.1f}%)')
