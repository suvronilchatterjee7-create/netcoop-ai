"""Config loading with justification enforcement (Part C1.1).

Every tunable value in ``config/*.yaml`` is a *parameter entry*: a mapping with
``value``, ``unit``, ``rationale`` and ``source``. Entries may be nested under
plain grouping keys. Loading fails if any leaf scalar is not wrapped in a
justified entry, so an unexplained magic number cannot enter the system.

Lists of plain identifiers (e.g. scenario family names taken verbatim from the
problem statement) are allowed under a ``catalog`` key, which must itself carry
``rationale`` and ``source``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

REQUIRED_PARAM_KEYS = frozenset({"value", "unit", "rationale", "source"})
REQUIRED_CATALOG_KEYS = frozenset({"catalog", "rationale", "source"})


class ConfigError(Exception):
    """Raised when a config file is missing, unparseable or unjustified."""


class Param(BaseModel):
    """A single justified configuration value."""

    model_config = ConfigDict(frozen=True)

    value: Any
    unit: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    source: str = Field(min_length=1)


def _validate_tree(node: Any, path: str) -> None:
    if isinstance(node, dict):
        keys = set(node)
        if keys >= REQUIRED_PARAM_KEYS:
            Param.model_validate(node)
            return
        if keys >= REQUIRED_CATALOG_KEYS:
            for k in ("rationale", "source"):
                if not str(node[k]).strip():
                    raise ConfigError(f"{path}: catalog '{k}' is empty")
            return
        if "value" in keys:
            missing = sorted(REQUIRED_PARAM_KEYS - keys)
            raise ConfigError(f"{path}: parameter entry missing {missing}")
        for key, child in node.items():
            if key in ("description", "_doc"):
                continue
            _validate_tree(child, f"{path}.{key}" if path else str(key))
        return
    raise ConfigError(
        f"{path}: bare value {node!r} is not allowed; wrap it as {{value, unit, rationale, source}}"
    )


def load_config(name: str, config_dir: Path | None = None) -> dict[str, Any]:
    """Load and validate ``<config_dir>/<name>.yaml``."""
    path = (config_dir or CONFIG_DIR) / f"{name}.yaml"
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    _validate_tree(data, name)
    return data


def get_value(cfg: dict[str, Any], dotted: str) -> Any:
    """Return the ``value`` of a parameter entry addressed by a dotted key."""
    node: Any = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ConfigError(f"config key not found: {dotted}")
        node = node[part]
    if isinstance(node, dict) and "value" in node:
        return node["value"]
    if isinstance(node, dict) and "catalog" in node:
        return node["catalog"]
    raise ConfigError(f"{dotted} is a group, not a parameter entry")


def config_hash(config_dir: Path | None = None) -> str:
    """Stable SHA-256 over all config files, for run manifests."""
    root = config_dir or CONFIG_DIR
    h = hashlib.sha256()
    for path in sorted(root.glob("*.yaml")):
        h.update(path.name.encode())
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        h.update(json.dumps(data, sort_keys=True, default=str).encode())
    return h.hexdigest()
