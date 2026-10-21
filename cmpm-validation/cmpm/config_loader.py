"""Load and validate config.yaml — the single source of truth for all assumptions."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load config.yaml and return the raw dict.

    Parameters
    ----------
    path : str | Path | None
        Override path.  Defaults to <project_root>/config.yaml.
    """
    if path is None:
        path = os.environ.get("CMPM_CONFIG", _DEFAULT_CONFIG_PATH)
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r") as fh:
        cfg = yaml.safe_load(fh)
    _validate(cfg)
    return cfg


def _validate(cfg: dict[str, Any]) -> None:
    """Minimal structural validation — fail fast on missing top-level keys."""
    required_sections = [
        "general", "projects", "score_weights", "frictions",
        "sensitivity", "monte_carlo", "electrical_project",
        "interactions", "optimization", "scoring", "baseline",
    ]
    for sec in required_sections:
        if sec not in cfg:
            raise KeyError(f"Missing required config section: '{sec}'")

    gen = cfg["general"]
    for key in ("discount_rate", "analysis_life_years", "random_seed", "monte_carlo_draws"):
        if key not in gen:
            raise KeyError(f"Missing general.{key}")

    if not (0 < gen["discount_rate"] < 1):
        raise ValueError(f"discount_rate must be in (0, 1), got {gen['discount_rate']}")
    if gen["analysis_life_years"] < 1:
        raise ValueError("analysis_life_years must be >= 1")

    weights = cfg["score_weights"]
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"score_weights must sum to 1.0, got {total}")


def get_project_list(cfg: dict[str, Any]) -> list[str]:
    """Return project keys in insertion order."""
    return list(cfg["projects"].keys())


def get_project(cfg: dict[str, Any], key: str) -> dict[str, Any]:
    """Return one project's config dict."""
    return cfg["projects"][key]
