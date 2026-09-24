"""Run configuration: the parcel registry, build parameters, and every path
derived from them. Pure data — no I/O.

A run is (Layout, BuildParams). Layout answers "where do this parcel's files
live"; BuildParams answers "which dataset, built how". Nothing in the pipeline
reads module-level mutable state, so a library caller and the CLI get the
same results.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from floodflow.parcels import generate_deanza_country_club, generate_deanza_villas

ROOT = Path(__file__).resolve().parent.parent
TARGET_CRS = "EPSG:5070"
BOOTSTRAP_BUFFER_M = 25_000.0

ALGORITHMS = ("d8", "dinf")
RESOLUTIONS = (1.0, 10.0)
HYDRO_STRATEGIES = ("breach_then_fill", "fill_only", "breach_only")
REACHABILITY_MODES = ("none", "boolean", "flow_weighted")


@dataclass(frozen=True)
class Parcel:
    key: str
    name: str
    boundary_file: str
    generate: Callable[[Path], Path]


PARCELS: dict[str, Parcel] = {p.key: p for p in [
    Parcel("country_club", "De Anza Country Club",
           "deanza_country_club_boundary.geojson", generate_deanza_country_club),
    Parcel("deanza_villas", "De Anza Villas",
           "deanza_villas_boundary.geojson", generate_deanza_villas),
]}
DEFAULT_PARCEL = "country_club"


@dataclass(frozen=True)
class Layout:
    """All paths for one parcel, rooted at `root` (the repo by default)."""
    parcel: Parcel
    root: Path = ROOT

    @classmethod
    def for_parcel(cls, key: str, root: Path = ROOT) -> Layout:
        return cls(PARCELS[key], Path(root))

    # -- inputs --
    @property
    def boundary(self) -> Path:
        return self.root / "data" / "raw" / "vectors" / self.parcel.boundary_file

    # -- derived (deleted by clean) --
    @property
    def runs_root(self) -> Path:
        return self.root / "data" / "derived" / "runs"

    @property
    def run_dir(self) -> Path:
        return self.runs_root / self.parcel.key

    @property
    def rasters(self) -> Path:
        return self.run_dir / "rasters"

    @property
    def vectors(self) -> Path:
        return self.run_dir / "vectors"

    @property
    def bootstrap(self) -> Path:
        return self.run_dir / "bootstrap"

    @property
    def contributing_area(self) -> Path:
        return self.vectors / "parcel_contributing_area.geojson"

    @property
    def contributing_area_5070(self) -> Path:
        return self.vectors / "parcel_contributing_area_5070.geojson"

    # -- published (read by docs/index.html) --
    @property
    def publish_root(self) -> Path:
        return self.root / "docs" / "data"

    @property
    def publish_dir(self) -> Path:
        return self.publish_root / self.parcel.key

    @property
    def manifest(self) -> Path:
        return self.publish_root / "manifest.json"


@dataclass(frozen=True)
class BuildParams:
    """Everything that determines a published dataset's contents."""
    resolution_m: float
    algorithm: str
    stream_threshold: int = 250
    threshold_frac: float | None = None
    hydro_strategy: str = "breach_then_fill"
    reachability_mode: str = "none"

    def __post_init__(self) -> None:
        if self.algorithm not in ALGORITHMS:
            raise ValueError(f"Unknown algorithm {self.algorithm!r}; choose from {ALGORITHMS}")
        if self.resolution_m not in RESOLUTIONS:
            raise ValueError(f"Unsupported resolution {self.resolution_m}; choose from {RESOLUTIONS}")
        if self.hydro_strategy not in HYDRO_STRATEGIES:
            raise ValueError(f"Unknown hydro strategy {self.hydro_strategy!r}")
        if self.reachability_mode not in REACHABILITY_MODES:
            raise ValueError(f"Unknown reachability mode {self.reachability_mode!r}")

    @property
    def res_tag(self) -> str:
        return f"{int(self.resolution_m)}m"

    @property
    def dataset_key(self) -> str:
        """Explorer/CLI name, e.g. 'dinf10m'."""
        return f"{self.algorithm}{self.res_tag}"

    @property
    def binary_name(self) -> str:
        suffix = "_frac" if self.reachability_mode == "flow_weighted" else ""
        return f"{self.algorithm}_{self.res_tag}{suffix}.bin"

    def to_dict(self) -> dict:
        return asdict(self)
