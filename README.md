
Flood risk depends on flow routing, and flow routing depends on which algorithm you pick and how much detail you feed it. This program will run locally on any area of interest.

**[→ Live explorer](https://rubicante.github.io/deanza-villas-flood-study/)**

---

## Stream Explorer

Pick a flow algorithm (D8 or D∞), a DEM resolution (1m or 10m), and a
drainage-area threshold (250 m² to 10 km², the same scale at both resolutions). The map shows which upstream terrain
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

All stream networks are extracted from flow accumulation rasters by cell-count thresholding (250 cells by default), then exported as drainage area so 1m and 10m are comparable. The 10m networks therefore start at 2.5 ha.

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
floodflow all                          # full run, default parcel
floodflow all --parcel deanza_villas   # alternate parcel

# Step by step
floodflow prepare          # contributing area
floodflow dinf1m           # D∞ 1m
floodflow dinf10m          # D∞ 10m
floodflow d81m             # D8 1m
floodflow d810m            # D8 10m

floodflow clean            # delete derived artifacts and published datasets
floodflow clean-all        # also delete DEM tile cache
```

`python -m floodflow …` works too. A dataset is rebuilt only when its build
settings (parcel, threshold, hydro strategy, …) differ from what
`docs/data/manifest.json` records, so there's no need to `clean` between runs.

---

## Parcels

Select at runtime with `--parcel`. Available options:

| Key | Description |
|---|---|
| `country_club` | De Anza Country Club (OSM way 44500984) — **default** |
| `deanza_villas` | De Anza Villas residential complex (SANDAG parcels) |

To add a parcel: implement a generator in `floodflow/parcels.py` and add an
entry to `PARCELS` in `floodflow/config.py`. Every published parcel shows up
in the explorer's parcel picker.

---

## Repository layout

```
floodflow/                   Hydrology library + pipeline CLI
floodflow/experimental/      Reachability filter (off by default; kept for study)
docs/                        Explorer (index.html), served by GitHub Pages
docs/data/manifest.json      What the explorer loads: parcels, datasets, layers
docs/data/<parcel>/          Stream binaries + parcel/contributing-area GeoJSON
scripts/                     One-off data fetch scripts
tests/                       pytest suite
data/raw/vectors/            Parcel boundaries (fetched on demand, not committed)
data/raw/dem/tiles/          Cached DEM tiles (not committed)
data/derived/runs/<parcel>/  Computed rasters + vectors (deleted by clean)
```

See [AGENTS.md](AGENTS.md) for pipeline conventions, key invariants, and
non-obvious tool behaviors.

---

## Environment

Python 3.12+ via `uv`.

```bash
uv venv && uv pip install -e ".[dev]"
pytest          # ~2 s; includes a tiny end-to-end WhiteboxTools run
ruff check .
git config core.hooksPath .githooks   # once per clone: lint + tests before each commit
```
