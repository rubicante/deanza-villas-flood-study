"""Design storms from NOAA Atlas 14 precipitation frequency estimates.

    atlas14(lat, lon)                    → PF table (depth by duration × ARI), cached
    PFTable.depth_mm(minutes, ari)       → log-log interpolated depth
    alternating_block(table, ...)        → hyetograph (m/s per block)

The PFDS service returns partial-duration-series depths for 19 durations
(5 min … 60 days) and 10 average recurrence intervals (1 … 1000 years). We
request inches because the metric response is rounded to whole millimetres.
Borrego Springs is in Atlas 14 Volume 6 (Southwest), version 2.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PFDS_URL = "https://hdsc.nws.noaa.gov/cgi-bin/new/cgi_readH5.py"
DURATIONS_MIN = (5, 10, 15, 30, 60, 120, 180, 360, 720, 1440,
                 2 * 1440, 3 * 1440, 4 * 1440, 7 * 1440, 10 * 1440,
                 20 * 1440, 30 * 1440, 45 * 1440, 60 * 1440)
ARI_YEARS = (1, 2, 5, 10, 25, 50, 100, 200, 500, 1000)
MM_PER_IN = 25.4


@dataclass(frozen=True)
class PFTable:
    lat: float
    lon: float
    depth_mm: np.ndarray            # (len(DURATIONS_MIN), len(ARI_YEARS))
    source: dict                    # volume, version, query time

    def column(self, ari: int) -> np.ndarray:
        if ari not in ARI_YEARS:
            raise ValueError(f"ARI {ari} not in Atlas 14 table {ARI_YEARS}")
        return self.depth_mm[:, ARI_YEARS.index(ari)]

    def depth_mm_at(self, minutes, ari: int) -> np.ndarray:
        """Depth for any duration(s) between 5 min and 60 days, interpolated
        linearly in log(duration)–log(depth)."""
        d = np.log(np.asarray(DURATIONS_MIN, dtype=float))
        return np.exp(np.interp(np.log(np.asarray(minutes, dtype=float)), d,
                                np.log(self.column(ari))))


def parse_pfds(text: str) -> tuple[np.ndarray, dict]:
    """Parse the PFDS JavaScript-ish response into (depth_in, metadata)."""
    m = re.search(r"quantiles\s*=\s*(\[\[.*?\]\]);", text, re.S)
    if not m:
        raise RuntimeError(f"No quantiles in PFDS response: {text[:200]!r}")
    table = np.array(json.loads(m.group(1).replace("'", '"')), dtype=float)
    if table.shape != (len(DURATIONS_MIN), len(ARI_YEARS)):
        raise RuntimeError(f"Unexpected PFDS table shape {table.shape}")
    meta = {k: v for k, v in re.findall(r"^(\w+)\s*=\s*'([^']*)';", text, re.M)
            if k in ("region", "volume", "version", "unit", "ser", "lat", "lon")}
    return table, meta


def atlas14(lat: float, lon: float, cache_dir: Path) -> PFTable:
    """Atlas 14 PDS depths at (lat, lon), cached as JSON in `cache_dir`."""
    cache = Path(cache_dir) / f"atlas14_pds_{lat:.4f}_{lon:.4f}.json"
    if cache.exists():
        doc = json.loads(cache.read_text())
    else:
        query = urllib.parse.urlencode({"lat": f"{lat:.4f}", "lon": f"{lon:.4f}", "type": "pf",
                                        "data": "depth", "units": "english", "series": "pds"})
        with urllib.request.urlopen(f"{PFDS_URL}?{query}", timeout=60) as resp:
            table_in, meta = parse_pfds(resp.read().decode())
        if meta.get("unit") != "english":
            raise RuntimeError(f"Expected inches from PFDS, got {meta.get('unit')!r}")
        doc = {"source": {**meta, "service": PFDS_URL,
                          "queried_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")},
               "durations_min": list(DURATIONS_MIN), "ari_years": list(ARI_YEARS),
               "depth_mm": (table_in * MM_PER_IN).round(2).tolist()}
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(doc, indent=1) + "\n")
    return PFTable(lat, lon, np.array(doc["depth_mm"]), doc["source"])


def alternating_block(table: PFTable, ari: int, duration_min: int,
                      block_min: int = 5, peak_frac: float = 0.5) -> np.ndarray:
    """Alternating-block hyetograph: rain rate (m/s) for each `block_min` block.

    Every centred window of k blocks around the peak holds exactly the Atlas 14
    depth for k × block_min minutes, so the storm is critical for every
    catchment response time up to `duration_min`. `peak_frac` places the peak
    (0.5 = centre)."""
    if duration_min % block_min:
        raise ValueError("duration must be a whole number of blocks")
    n = duration_min // block_min
    cum = table.depth_mm_at(block_min * np.arange(1, n + 1), ari)
    inc = np.diff(cum, prepend=0.0)                    # largest first
    order = np.empty(n, dtype=int)
    peak = min(n - 1, int(peak_frac * n))
    left, right = peak - 1, peak + 1
    order[0] = peak
    for k in range(1, n):
        # Alternate right/left, spilling to whichever side still has room
        if (k % 2 == 1 and right < n) or left < 0:
            order[k] = right
            right += 1
        else:
            order[k] = left
            left -= 1
    blocks = np.empty(n)
    blocks[order] = inc
    return blocks * 1e-3 / (block_min * 60.0)
