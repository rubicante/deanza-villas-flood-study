"""
Stream extraction.

Key spike lessons:
  - WBT extract_streams with zero_background=True
"""

import time
from pathlib import Path

import rasterio

from floodflow import wbt


def extract_streams(
    accum: Path,
    threshold: int = 250,
    output: Path = Path("streams.tif"),
) -> Path:
    """
    Extract stream raster via WBT extract_streams.
    Returns output Path with binary (0/1) stream mask.
    """
    accum = Path(accum).resolve()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    wbt.run("ExtractStreams", output, flow_accum=accum, threshold=threshold,
            zero_background=True)

    with rasterio.open(output) as src:
        n_stream = int((src.read(1) > 0).sum())
    print(f"  Extract streams t={threshold}: {time.time()-t0:.0f}s ({n_stream:,} cells)")
    return output
