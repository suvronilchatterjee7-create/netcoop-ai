"""Controlled vocabulary: canonical metrics, units, entity types and hypothesis types.

The vocabulary is data (``data/vocabulary/*.yaml``), loaded and validated here. Protocol
payloads validate metric names, units, entity types and hypothesis types against it, so
every agent speaks the same terms. Its version is the envelope ``schema_version``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

VOCAB_DIR = Path(__file__).resolve().parents[2] / "data" / "vocabulary"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MetricDef(_Frozen):
    description: str
    unit: str
    kind: Literal["numeric", "enum"]
    values: tuple[str, ...] = ()
    applies_to: tuple[str, ...]
    worse_when: Literal["higher", "lower", "categorical", "none"]
    range: tuple[float | None, float | None] | None
    range_source: str

    @model_validator(mode="after")
    def _enum_has_values(self) -> MetricDef:
        if self.kind == "enum" and not self.values:
            raise ValueError("enum metric needs values")
        return self

    def in_range(self, v: float) -> bool:
        if self.range is None:
            return True
        lo, hi = self.range
        return (lo is None or v >= lo) and (hi is None or v <= hi)


class UnitDef(_Frozen):
    factor: float
    aliases: tuple[str, ...] = ()


class DimensionDef(_Frozen):
    canonical: str
    units: dict[str, UnitDef]


class EntityTypeDef(_Frozen):
    category: Literal["device", "link", "service", "segment"]
    description: str


class HypothesisTypeDef(_Frozen):
    kind: Literal["fault", "outcome"]
    family: str | None
    description: str


class Vocabulary(_Frozen):
    version: str
    metrics: dict[str, MetricDef]
    dimensions: dict[str, DimensionDef]
    entity_types: dict[str, EntityTypeDef]
    hypothesis_types: dict[str, HypothesisTypeDef]
    canonical_units: frozenset[str] = Field(default=frozenset())

    @model_validator(mode="after")
    def _cross_check(self) -> Vocabulary:
        canon = frozenset(d.canonical for d in self.dimensions.values())
        object.__setattr__(self, "canonical_units", canon)
        categories = {e.category for e in self.entity_types.values()}
        for name, m in self.metrics.items():
            if m.unit not in canon:
                raise ValueError(f"metric {name}: unit {m.unit!r} is not a canonical unit")
            bad = set(m.applies_to) - categories
            if bad:
                raise ValueError(f"metric {name}: unknown entity categories {sorted(bad)}")
        for need in ("normal", "insufficient_evidence"):
            if self.hypothesis_types.get(need, None) is None:
                raise ValueError(f"hypothesis type {need!r} is mandatory")
        return self

    # -- lookups -----------------------------------------------------------------
    def category_of(self, entity_type: str) -> str:
        return self.entity_types[entity_type].category

    def metric_applies(self, metric: str, entity_type: str) -> bool:
        return self.category_of(entity_type) in self.metrics[metric].applies_to

    def fault_types(self) -> list[str]:
        return [k for k, v in self.hypothesis_types.items() if v.kind == "fault"]


def _read(path: Path) -> dict:  # type: ignore[type-arg]
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "version" not in data:
        raise ValueError(f"{path}: vocabulary file must be a mapping with 'version'")
    return data


def load_vocabulary(vocab_dir: Path = VOCAB_DIR) -> Vocabulary:
    files = {
        name: _read(vocab_dir / f"{name}.yaml")
        for name in ("metrics", "units", "entity_types", "hypothesis_types")
    }
    versions = {d["version"] for d in files.values()}
    if len(versions) != 1:
        raise ValueError(f"vocabulary files disagree on version: {sorted(versions)}")
    return Vocabulary(
        version=versions.pop(),
        metrics=files["metrics"]["metrics"],
        dimensions=files["units"]["dimensions"],
        entity_types=files["entity_types"]["entity_types"],
        hypothesis_types=files["hypothesis_types"]["hypothesis_types"],
    )


@lru_cache(maxsize=1)
def get_vocabulary() -> Vocabulary:
    """Process-wide vocabulary used by protocol validators."""
    return load_vocabulary()
