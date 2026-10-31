"""Declarative field mapping (data/mappings/canonical.yaml) and unit resolution."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from netcoop.protocol.vocabulary import Vocabulary, get_vocabulary

MAPPING_PATH = Path(__file__).resolve().parents[2] / "data" / "mappings" / "canonical.yaml"
_NON_ALNUM = re.compile(r"[^0-9a-z]+")


@lru_cache(maxsize=4096)
def normalise_key(key: str) -> str:
    """'Latency-MS ' -> 'latency_ms'. Applied to every source field name before lookup."""
    return _NON_ALNUM.sub("_", str(key).strip().lower()).strip("_")


@dataclass(frozen=True)
class MetricAlias:
    metric: str
    unit: str | None  # declared unit, None = detect
    scope: str | None  # entity category the alias is restricted to


@dataclass(frozen=True)
class Binding:
    name: str
    entity_type: str
    id_fields: tuple[str, ...] = ()
    endpoint_fields: tuple[tuple[str, str], ...] = ()
    observed_from_fields: tuple[str, ...] = ()
    value_case: str | None = None


@dataclass(frozen=True)
class UnitInfo:
    name: str  # canonical spelling of this unit, e.g. 'us'
    dimension: str
    factor: float  # multiply to get the dimension's canonical unit


@dataclass
class Mapping:
    version: str
    timestamp_fields: frozenset[str]
    schema_version_fields: frozenset[str]
    context_fields: frozenset[str]
    bindings: tuple[Binding, ...]
    metric_aliases: dict[str, tuple[MetricAlias, ...]]
    enum_values: dict[str, dict[str, str]]
    topology: dict[str, Any]
    dialect_profiles: dict[str, dict[str, Any]]
    units: dict[str, UnitInfo] = field(default_factory=dict)

    # -- field classification -----------------------------------------------------
    def metric_for(self, key: str, category: str | None) -> MetricAlias | None:
        """Resolve a normalised field name to a metric alias for an entity category."""
        candidates = self.metric_aliases.get(key, ())
        scoped = [a for a in candidates if a.scope is None or a.scope == category]
        return scoped[0] if scoped else None

    def is_known(self, key: str) -> bool:
        return (
            key in self.timestamp_fields
            or key in self.schema_version_fields
            or key in self.context_fields
            or key in self.metric_aliases
            or any(
                key in b.id_fields
                or key in b.observed_from_fields
                or any(key in p for p in b.endpoint_fields)
                for b in self.bindings
            )
        )

    def all_known_keys(self) -> list[str]:
        keys = (
            set(self.timestamp_fields) | set(self.schema_version_fields) | set(self.context_fields)
        )
        keys |= set(self.metric_aliases)
        for b in self.bindings:
            keys |= set(b.id_fields) | set(b.observed_from_fields)
            for p in b.endpoint_fields:
                keys |= set(p)
        return sorted(keys)

    def suggest(self, key: str, cutoff: float) -> str | None:
        """'Did you mean' for an unknown field. Reported only, never applied."""
        hits = difflib.get_close_matches(key, self.all_known_keys(), n=1, cutoff=cutoff)
        return hits[0] if hits else None

    # -- units ---------------------------------------------------------------------
    def unit(self, name: str | None) -> UnitInfo | None:
        if name is None:
            return None
        return self.units.get(name) or self.units.get(name.lower())

    def unit_from_suffix(self, key: str, dimension: str) -> UnitInfo | None:
        """Unit encoded in the last '_' token of a field name, if of the right dimension."""
        token = key.rsplit("_", 1)[-1] if "_" in key else None
        info = self.unit(token) if token else None
        return info if info is not None and info.dimension == dimension else None

    def detect_dialect(self, keys: set[str]) -> str:
        best, best_score = "unrecognised", 0.0
        for name, prof in self.dialect_profiles.items():
            sig = set(prof["signature"])
            score = len(sig & keys) / len(sig | keys) if sig | keys else 0.0
            if score > best_score:
                best, best_score = name, score
        return best


def _build_units(vocab: Vocabulary) -> dict[str, UnitInfo]:
    table: dict[str, UnitInfo] = {}
    for dim_name, dim in vocab.dimensions.items():
        for unit_name, u in dim.units.items():
            info = UnitInfo(unit_name, dim_name, u.factor)
            for spelling in (unit_name, *u.aliases):
                table[spelling] = info
                table.setdefault(spelling.lower(), info)
                table.setdefault(normalise_key(spelling), info)
    return table


def load_mapping(path: Path = MAPPING_PATH, vocab: Vocabulary | None = None) -> Mapping:
    vocab = vocab or get_vocabulary()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    norm = normalise_key

    aliases: dict[str, list[MetricAlias]] = {}
    for metric, spec in raw["metrics"].items():
        if metric not in vocab.metrics:
            raise ValueError(f"mapping refers to unknown metric {metric!r}")
        for alias, unit in spec["aliases"].items():
            aliases.setdefault(norm(alias), []).append(MetricAlias(metric, unit, spec.get("scope")))

    bindings = []
    for b in raw["entity_bindings"]:
        bindings.append(
            Binding(
                name=b["name"],
                entity_type=b["entity_type"],
                id_fields=tuple(norm(x) for x in b.get("id_fields", [])),
                endpoint_fields=tuple((norm(a), norm(z)) for a, z in b.get("endpoint_fields", [])),
                observed_from_fields=tuple(norm(x) for x in b.get("observed_from_fields", [])),
                value_case=b.get("value_case"),
            )
        )
    mapping = Mapping(
        version=str(raw["version"]),
        timestamp_fields=frozenset(norm(x) for x in raw["record_fields"]["timestamp"]),
        schema_version_fields=frozenset(norm(x) for x in raw["record_fields"]["schema_version"]),
        context_fields=frozenset(norm(x) for x in raw.get("context_fields", [])),
        bindings=tuple(bindings),
        metric_aliases={k: tuple(v) for k, v in aliases.items()},
        enum_values={
            m: {str(k).lower(): v for k, v in vals.items()}
            for m, vals in raw["enum_values"].items()
        },
        topology=raw["topology"],
        dialect_profiles=raw.get("dialect_profiles", {}),
        units=_build_units(vocab),
    )
    for alias_list in mapping.metric_aliases.values():
        for a in alias_list:
            if a.unit is not None and mapping.unit(a.unit) is None:
                raise ValueError(f"mapping alias for {a.metric} declares unknown unit {a.unit!r}")
    return mapping


@lru_cache(maxsize=1)
def get_mapping() -> Mapping:
    return load_mapping()
