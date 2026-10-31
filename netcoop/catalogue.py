"""Hypothesis catalogue and specialist definitions (config/catalogue/*.yaml)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from netcoop.config import CONFIG_DIR
from netcoop.protocol.vocabulary import get_vocabulary

CATALOGUE_DIR = CONFIG_DIR / "catalogue"

Scope = Literal[
    "root",
    "root_upstream",
    "root_downstream",
    "root_endpoints",
    "attached_links",
    "probes_of_root",
    "probes_from_root",
    "probes_downstream",
    "probe_paths",
]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Element(_Model):
    metric: str
    expect: Literal["deviates", "normal"]
    direction: Literal["above", "below", "changed", "rising"]
    scope: Scope
    role: Literal["required", "supporting"]
    group: str | None = None
    quorum: float | None = Field(default=None, gt=0, le=1)

    @property
    def group_key(self) -> str:
        return self.group or f"{self.metric}:{self.direction}:{self.scope}"


class Locus(_Model):
    category: Literal["link", "device", "service"]
    entity_types: tuple[str, ...] = ()
    entity_ids: tuple[str, ...] = ()  # for services: names the hypothesis applies to

    def admits(self, entity_id: str, entity_type: str) -> bool:
        vocab = get_vocabulary()
        if vocab.category_of(entity_type) != self.category:
            return False
        if self.entity_types and entity_type not in self.entity_types:
            return False
        return not self.entity_ids or entity_id.lower() in self.entity_ids


class HypothesisSpec(_Model):
    id: str
    description: str
    locus: Locus
    signature: tuple[Element, ...]
    competes_with: tuple[str, ...] = ()
    explains: tuple[str, ...] = ()
    actions: tuple[str, ...]
    rationale: str
    source: str

    @property
    def required(self) -> tuple[Element, ...]:
        return tuple(e for e in self.signature if e.role == "required")

    def metrics(self) -> set[str]:
        return {e.metric for e in self.signature}

    def required_metrics(self) -> set[str]:
        return {e.metric for e in self.required}


class SpecialistSpec(_Model):
    id: str
    description: str
    metrics: tuple[str, ...]
    optional: bool
    rationale: str
    source: str


class Catalogue(_Model):
    version: str
    hypotheses: dict[str, HypothesisSpec]

    @model_validator(mode="after")
    def _check(self) -> Catalogue:
        vocab = get_vocabulary()
        for h in self.hypotheses.values():
            if (
                vocab.hypothesis_types.get(h.id) is None
                or vocab.hypothesis_types[h.id].kind != "fault"
            ):
                raise ValueError(f"catalogue entry {h.id!r} is not a fault type in the vocabulary")
            if not h.required:
                raise ValueError(f"{h.id}: needs at least one required signature element")
            for e in h.signature:
                if e.metric not in vocab.metrics:
                    raise ValueError(f"{h.id}: unknown metric {e.metric!r}")
            for other in (*h.competes_with, *h.explains):
                if other not in self.hypotheses:
                    raise ValueError(f"{h.id}: relation to unknown hypothesis {other!r}")
        return self


def _read(name: str, base: Path) -> dict:  # type: ignore[type-arg]
    data: dict = yaml.safe_load((base / name).read_text(encoding="utf-8"))  # type: ignore[type-arg]
    return data


def load_catalogue(base: Path = CATALOGUE_DIR) -> Catalogue:
    raw = _read("hypotheses.yaml", base)
    return Catalogue(
        version=str(raw["version"]),
        hypotheses={k: HypothesisSpec(id=k, **v) for k, v in raw["hypotheses"].items()},
    )


def load_specialists(base: Path = CATALOGUE_DIR) -> list[SpecialistSpec]:
    raw = _read("agents.yaml", base)
    vocab = get_vocabulary()
    out = []
    for k, v in raw["specialists"].items():
        spec = SpecialistSpec(id=k, **v)
        bad = set(spec.metrics) - set(vocab.metrics)
        if bad:
            raise ValueError(f"specialist {k}: unknown metrics {sorted(bad)}")
        out.append(spec)
    return out


@lru_cache(maxsize=1)
def get_catalogue() -> Catalogue:
    return load_catalogue()
