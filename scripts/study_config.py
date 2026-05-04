from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
# Ensure repo root is importable from step scripts run as __main__
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CONFIG_DIR = ROOT / "config"
STUDY_CONFIG_PATH = CONFIG_DIR / "study.yaml"
STUDY_MANIFEST_PATH = CONFIG_DIR / "study_manifest.yaml"


@lru_cache(maxsize=1)
def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def study_config() -> dict[str, Any]:
    return load_yaml(STUDY_CONFIG_PATH)


@lru_cache(maxsize=1)
def study_manifest() -> dict[str, Any]:
    return load_yaml(STUDY_MANIFEST_PATH)


def resolve_relative(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (ROOT / path)


def config_path(*keys: str) -> Path:
    node: Any = study_config()
    for key in keys:
        node = node[key]
    return resolve_relative(node)


def config_value(*keys: str) -> Any:
    node: Any = study_config()
    for key in keys:
        node = node[key]
    return node


def step_path(*keys: str) -> Path:
    return config_path("steps", *keys)


def deliverable_path(*keys: str) -> Path:
    node: Any = study_manifest()
    for key in ("canonical_deliverables", *keys):
        node = node[key]
    return resolve_relative(node)


TARGET_CRS = config_value("study", "crs")
DEFAULT_THRESHOLDS = list(config_value("study", "default_thresholds"))
