
Flood risk depends on flow routing, and flow routing depends on which algorithm you pick and how much detail you feed it. This program will run locally on any area of interest.

**[→ Live explorer](https://rubicante.github.io/deanza-villas-flood-study/)**

---

## Stream Explorer

Pick a flow algorithm (D8 or D∞), a DEM resolution (1m or 10m), and an
accumulation threshold (250–100k cells). The map shows which upstream terrain
drains toward the parcel under those assumptions. Tweak the threshold to see
fine distributary detail or just the major channels.

### Input

- **Parcel boundary**: A polygon representing our area of interest. Default is the De Anza Country Club golf course.

### Output

- **Contributing area**: Upstream cells that drain into the parcel
- **D8 1m stream network**: D8 flow accumulation on 1m DEM
- **D8 10m stream network**: D8 flow accumulation on 10m DEM
- **D∞ 1m stream network**: D∞ flow accumulation on 1m DEM
- **D∞ 10m stream network**: D∞ flow accumulation on 10m DEM

All stream networks are extracted from flow accumulation rasters by cell-count thresholding.

### Reference layers

| Layer | Source |
|---|---|
| Borrego Palm Canyon watershed (USGS) | Watershed Boundary Dataset, HUC-12 181002030302 |
| Flood zones (FEMA) | National Flood Hazard Layer, DFIRM 06073C (Nov 2023) |

---

## Generating the data

The pipeline fetches terrain data, computes flow direction and accumulation,
and writes the binary stream files the explorer loads.

```bash
source .venv/bin/activate

python -m deliverable._pipeline all              # full run, default parcel
python -m deliverable._pipeline all --parcel deanza_villas   # alternate parcel

# Step by step
python -m deliverable._pipeline prepare          # contributing area
python -m deliverable._pipeline dinf1m           # D∞ 1m
python -m deliverable._pipeline dinf10m          # D∞ 10m
python -m deliverable._pipeline d81m             # D8 1m
python -m deliverable._pipeline d810m            # D8 10m

python -m deliverable._pipeline clean            # delete derived artifacts
python -m deliverable._pipeline clean-all        # also delete DEM tile cache
```

---

## Parcels

Select at runtime with `--parcel`. Available options:

| Key | Description |
|---|---|
| `country_club` | De Anza Country Club (OSM way 44500984) — **default** |
| `deanza_villas` | De Anza Villas residential complex (SANDAG parcels) |

To add a parcel: implement a generator in `deliverable/parcels.py` and add an
entry to `_PARCELS` in `_pipeline.py`.

---

## Repository layout

```
deliverable/          Hydrology library + pipeline CLI
docs/                 Explorer (index.html) + binary stream data + GeoJSON layers
scripts/              One-off data fetch scripts
data/raw/vectors/     Parcel boundaries (fetched on demand, not committed)
data/raw/dem/tiles/   Cached DEM tiles (not committed)
data/derived/         Computed rasters + vectors (deleted by clean)
```

See [AGENTS.md](AGENTS.md) for pipeline conventions, key invariants, and
non-obvious tool behaviors.

---

## Environment

Python 3.12 via `uv`.

```bash
uv pip install -r deliverable/requirements.txt
```
