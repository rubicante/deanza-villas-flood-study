"""Command-line interface: `floodflow <command> [options]` (or `python -m floodflow`)."""

from __future__ import annotations

import argparse
import sys

from floodflow.config import (
    DEFAULT_PARCEL,
    HYDRO_STRATEGIES,
    PARCELS,
    REACHABILITY_MODES,
    BuildParams,
    Layout,
)
from floodflow.pipeline import build, clean, clean_all, prepare

# Build commands → (resolution_m, algorithm). Order is the `all` build order.
DATASETS: dict[str, tuple[float, str]] = {
    "dinf1m": (1.0, "dinf"),
    "dinf10m": (10.0, "dinf"),
    "d81m": (1.0, "d8"),
    "d810m": (10.0, "d8"),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="floodflow",
        description="Build parcel-centered stream datasets for the explorer.")
    parser.add_argument(
        "command", choices=["prepare", *DATASETS, "all", "clean", "clean-all"],
        help="Which step to run.")
    parser.add_argument(
        "--threshold", type=int, default=250,
        help="Stream extraction accumulation threshold in cells (default: 250).")
    parser.add_argument(
        "--threshold-frac", type=float, default=None,
        help="Stream extraction threshold as fraction of contributing area cells "
             "(e.g. 0.0001 for 0.01%%). Overrides --threshold.")
    parser.add_argument(
        "--hydro", choices=HYDRO_STRATEGIES, default="breach_then_fill",
        help="DEM preprocessing strategy (default: breach_then_fill).")
    parser.add_argument(
        "--reachability", choices=REACHABILITY_MODES, default="none",
        help="Reachability mode (experimental): none (default, all CA streams), "
             "boolean, or flow_weighted (D∞ only).")
    parser.add_argument(
        "--parcel", choices=list(PARCELS), default=DEFAULT_PARCEL,
        help=f"Parcel to analyse (default: {DEFAULT_PARCEL}).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "clean":
        clean()
        return 0
    if args.command == "clean-all":
        clean_all()
        return 0

    layout = Layout.for_parcel(args.parcel)

    def run(key: str) -> None:
        resolution, algorithm = DATASETS[key]
        build(layout, BuildParams(
            resolution_m=resolution, algorithm=algorithm,
            stream_threshold=args.threshold, threshold_frac=args.threshold_frac,
            hydro_strategy=args.hydro, reachability_mode=args.reachability))

    if args.command == "prepare":
        prepare(layout)
    elif args.command == "all":
        prepare(layout)
        for key in DATASETS:
            run(key)
    else:
        run(args.command)
    return 0


if __name__ == "__main__":
    sys.exit(main())
