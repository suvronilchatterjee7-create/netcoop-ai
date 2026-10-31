"""Shared protocol building blocks: enums, base model and small value types.

Every field carries a ``description`` and, where it has one, a ``unit`` (exported into the
JSON Schema as ``x-unit``). ``docs/PROTOCOL_REFERENCE.md`` is generated from these.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.config import JsonDict

from netcoop.protocol.vocabulary import get_vocabulary

PROTOCOL_NAME = "netcoop"
# The wire-format version these models implement. It identifies the code, so it is a
# constant, not a tunable; supported versions and adapters live in versioning.py.
PROTOCOL_VERSION = "2.0"
BOARD = "board"


def F(description: str, unit: str | None = None, **kw: Any) -> Any:
    """Field with mandatory description and optional unit metadata."""
    extra: JsonDict | None = {"x-unit": unit} if unit else None
    return Field(description=description, json_schema_extra=extra, **kw)


class ProtocolModel(BaseModel):
    """Base for all protocol models: immutable, no unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid", use_enum_values=False)


class MessageType(StrEnum):
    OBSERVATION = "OBSERVATION"
    TOPOLOGY = "TOPOLOGY"
    CLUE = "CLUE"
    HYPOTHESIS = "HYPOTHESIS"
    SUPPORT = "SUPPORT"
    CONTRADICT = "CONTRADICT"
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    ERROR = "ERROR"
    ACK = "ACK"
    CAPABILITY = "CAPABILITY"
    VERDICT = "VERDICT"
    REPORT = "REPORT"


class Severity(StrEnum):
    FATAL = "fatal"  # the input or task cannot be used at all
    RECOVERABLE = "recoverable"  # part of the input was dropped or repaired
    WARNING = "warning"  # usable as is, but quality is reduced


class ErrorCode(StrEnum):
    MALFORMED_INPUT = "MALFORMED_INPUT"
    MISSING_FIELD = "MISSING_FIELD"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    UNKNOWN_UNIT = "UNKNOWN_UNIT"
    AMBIGUOUS_UNIT = "AMBIGUOUS_UNIT"
    IMPLAUSIBLE_VALUE = "IMPLAUSIBLE_VALUE"
    STALE_DATA = "STALE_DATA"
    CLOCK_SKEW = "CLOCK_SKEW"
    UNKNOWN_ENTITY = "UNKNOWN_ENTITY"
    MISSING_TOPOLOGY = "MISSING_TOPOLOGY"
    INCOMPATIBLE_SCHEMA = "INCOMPATIBLE_SCHEMA"
    INCOMPATIBLE_VERSION = "INCOMPATIBLE_VERSION"
    UNSUPPORTED_MESSAGE_TYPE = "UNSUPPORTED_MESSAGE_TYPE"
    UNSUPPORTED_REQUEST = "UNSUPPORTED_REQUEST"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    AGENT_FAILURE = "AGENT_FAILURE"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    DUPLICATE_SAMPLE = "DUPLICATE_SAMPLE"
    INAPPLICABLE_METRIC = "INAPPLICABLE_METRIC"


class Direction(StrEnum):
    ABOVE = "above"
    BELOW = "below"
    CHANGED = "changed"  # categorical change, e.g. status up -> down


class ComparisonBasis(StrEnum):
    THRESHOLD = "threshold"  # fixed, cited threshold from config
    BASELINE = "baseline"  # statistical baseline (calibrated or in-window)


class Statistic(StrEnum):
    MEAN = "mean"
    MEDIAN = "median"
    MAX = "max"
    MIN = "min"
    LAST = "last"
    SLOPE = "slope"
    FRACTION = "fraction"  # share of samples in a state / above a level
    UNSPECIFIED = "unspecified"  # source did not say (e.g. upgraded v1.0 clue)


class EntityRole(StrEnum):
    ROOT = "root"  # proposed location of the cause
    SYMPTOM = "symptom"  # shows effects of the cause
    CONTEXT = "context"  # related but not itself faulty (e.g. common upstream)


class Decision(StrEnum):
    DIAGNOSED = "diagnosed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NO_FAULT_DETECTED = "no_fault_detected"


# ----------------------------------------------------------------------------- values
class EntityRef(ProtocolModel):
    entity_id: str = F(
        "Identifier of the entity exactly as it appears in the input data.", min_length=1
    )
    entity_type: str = F("Entity type from the controlled vocabulary (entity_types.yaml).")

    @field_validator("entity_type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if v not in get_vocabulary().entity_types:
            raise ValueError(f"unknown entity_type {v!r}")
        return v


class TimeWindow(ProtocolModel):
    start: AwareDatetime = F("Start of the window (inclusive), ISO-8601 with timezone.")
    end: AwareDatetime = F("End of the window (inclusive), ISO-8601 with timezone.")

    @model_validator(mode="after")
    def _ordered(self) -> TimeWindow:
        if self.end < self.start:
            raise ValueError("window end precedes start")
        return self


class SourceRef(ProtocolModel):
    source: str = F("Input file or stream name the data came from.")
    dialect: str = F("Detected input dialect / mapping profile used to read it.")
    locator: str = F("Position inside the source, e.g. 'line:42' or 'row:7'.")
    raw_field: str | None = F("Original field name before mapping, if different.", default=None)


class DataQuality(ProtocolModel):
    score: float = F(
        "Overall quality (combination documented in docs/SCORING.md).", "ratio", ge=0, le=1
    )
    completeness: float = F("Share of expected samples/fields present.", "ratio", ge=0, le=1)
    freshness: float = F("1 = current, decays with staleness.", "ratio", ge=0, le=1)
    plausibility: float = F("Share of values inside physical ranges.", "ratio", ge=0, le=1)
    mapping_certainty: float = F(
        "1 = exact field/unit mapping; lower when inferred.", "ratio", ge=0, le=1
    )
    issues: tuple[str, ...] = F("Machine-readable issue codes (ErrorCode values).", default=())


def check_metric(metric: str, unit: str, entity: EntityRef | None) -> None:
    """Validate a metric/unit/entity combination against the vocabulary."""
    vocab = get_vocabulary()
    mdef = vocab.metrics.get(metric)
    if mdef is None:
        raise ValueError(f"unknown metric {metric!r}")
    if unit != mdef.unit:
        raise ValueError(f"metric {metric!r} must use canonical unit {mdef.unit!r}, got {unit!r}")
    if entity is not None and not vocab.metric_applies(metric, entity.entity_type):
        raise ValueError(f"metric {metric!r} does not apply to entity_type {entity.entity_type!r}")


def check_value(metric: str, value: float | str) -> None:
    mdef = get_vocabulary().metrics[metric]
    if mdef.kind == "enum":
        if value not in mdef.values:
            raise ValueError(f"{metric}: {value!r} not in {list(mdef.values)}")
    elif isinstance(value, str) or not mdef.in_range(float(value)):
        raise ValueError(f"{metric}: value {value!r} outside physical range {mdef.range}")
