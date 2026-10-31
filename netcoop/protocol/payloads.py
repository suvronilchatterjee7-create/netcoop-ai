"""Payload models, one per message type (see docs/PROTOCOL.md)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, field_validator, model_validator

from netcoop.protocol.capability import CapabilityCard
from netcoop.protocol.common import (
    ComparisonBasis,
    DataQuality,
    Decision,
    Direction,
    EntityRef,
    EntityRole,
    ErrorCode,
    F,
    ProtocolModel,
    Severity,
    SourceRef,
    Statistic,
    TimeWindow,
    check_metric,
    check_value,
)
from netcoop.protocol.report import Report
from netcoop.protocol.vocabulary import get_vocabulary

Scalar = str | float | int | bool


# ----------------------------------------------------------------------------- telemetry
class Point(ProtocolModel):
    t: AwareDatetime = F("Sample timestamp, ISO-8601 UTC.")
    v: float | str = F("Sample value in the observation's canonical unit (str for enum metrics).")
    src: int | None = F(
        "Index into the observation's `sources` list for this sample.", default=None
    )


class ObservationPayload(ProtocolModel):
    """A canonical time series of one metric on one entity (output of the Translator)."""

    entity: EntityRef = F("Entity the metric describes.")
    metric: str = F("Canonical metric name (metrics.yaml).")
    unit: str = F("Canonical unit of the metric; must equal the vocabulary unit.")
    observed_from: str | None = F(
        "Vantage point entity_id for probe-style metrics (e.g. service checks).", default=None
    )
    points: tuple[Point, ...] = F("Samples in time order.", min_length=1)
    sources: tuple[SourceRef, ...] = F("Where the samples came from (provenance).", default=())
    quality: DataQuality = F("Data-quality assessment of this series.")

    @model_validator(mode="after")
    def _check(self) -> ObservationPayload:
        check_metric(self.metric, self.unit, self.entity)
        for p in self.points:
            check_value(self.metric, p.v)
            if p.src is not None and not 0 <= p.src < len(self.sources):
                raise ValueError(f"point src index {p.src} out of range")
        ts = [p.t for p in self.points]
        if ts != sorted(ts):
            raise ValueError("points must be in time order")
        return self


class TopologyNode(ProtocolModel):
    entity: EntityRef = F("The node.")
    attributes: dict[str, Scalar] = F("Free-form source attributes (zone, tier, ...).", default={})


class TopologyEdge(ProtocolModel):
    link_id: str = F("entity_id of the link entity this edge represents.", min_length=1)
    a: str = F("entity_id of one endpoint (the upstream end when `directed`).")
    b: str = F("entity_id of the other endpoint (the downstream end when `directed`).")
    directed: bool = F("True if a is known to be upstream of b.")
    capacity: float | None = F("Nominal capacity.", "Mbit/s", default=None, ge=0)


class TopologyPayload(ProtocolModel):
    """The network graph as reported by the input data."""

    nodes: tuple[TopologyNode, ...] = F("All known devices/services.")
    edges: tuple[TopologyEdge, ...] = F("All known links.")
    upstream_root: str | None = F("entity_id of the topology root (core), if known.", default=None)
    sources: tuple[SourceRef, ...] = F("Where the topology came from.", default=())
    quality: DataQuality = F("Data-quality assessment of the topology.")

    @model_validator(mode="after")
    def _referential(self) -> TopologyPayload:
        ids = {n.entity.entity_id for n in self.nodes}
        for e in self.edges:
            missing = {e.a, e.b} - ids
            if missing:
                raise ValueError(f"edge {e.link_id} references unknown nodes {sorted(missing)}")
        if self.upstream_root is not None and self.upstream_root not in ids:
            raise ValueError("upstream_root is not a node")
        return self


# ----------------------------------------------------------------------------- reasoning
class Comparison(ProtocolModel):
    basis: ComparisonBasis = F(
        "Whether the value was compared with a fixed threshold or a baseline."
    )
    reference_value: float | str | None = F(
        "The threshold or baseline centre used, in the clue's unit.", default=None
    )
    spread: float | None = F(
        "Baseline spread (e.g. scaled MAD) used for normalisation.", default=None
    )
    config_key: str = F("Config key (or calibration key) the reference came from.", min_length=1)
    method: str = F("Detector that produced the comparison (documented in docs/SCORING.md).")


class CluePayload(ProtocolModel):
    """One piece of evidence: a metric on an entity deviates (or explicitly does not)."""

    entity: EntityRef = F("Entity the evidence is about.")
    metric: str = F("Canonical metric name.")
    statistic: Statistic = F("How `value` summarises the window.")
    value: float | str = F(
        "Summary value. Level stats: metric unit; slope: unit/interval; fraction: ratio."
    )
    unit: str = F("Unit of `value` (see `statistic`).")
    comparison: Comparison = F("What `value` was compared with.")
    direction: Direction = F("Direction of the deviation relative to the reference.")
    deviation: float = F("Normalised deviation magnitude (see `deviation_unit`); 0 = none.", ge=0)
    deviation_unit: str = F("Normalisation used, e.g. 'robust_z', 'ratio', 'percentage_points'.")
    significant: bool = F(
        "Detector judged the deviation significant (False = explicit negative evidence)."
    )
    persistence: float | None = F(
        "Share of window samples that deviate; null if unknown.", "ratio", default=None, ge=0, le=1
    )
    window: TimeWindow = F("Time window the evidence covers.")
    observed_from: str | None = F("Vantage point, for probe-style metrics.", default=None)
    source_observation_ids: tuple[str, ...] = F("msg_ids of the OBSERVATIONs used.", min_length=1)
    data_quality: float = F("Quality of the underlying observations.", "ratio", ge=0, le=1)

    @model_validator(mode="after")
    def _check(self) -> CluePayload:
        canonical = get_vocabulary().metrics.get(self.metric)
        if canonical is None:
            raise ValueError(f"unknown metric {self.metric!r}")
        expected = {
            Statistic.SLOPE: f"{canonical.unit}/interval",
            Statistic.FRACTION: "ratio",
        }.get(self.statistic, canonical.unit)
        if self.unit != expected:
            raise ValueError(
                f"clue unit for {self.statistic.value} of {self.metric} must be {expected!r}"
            )
        check_metric(self.metric, canonical.unit, self.entity)
        return self


class HypothesisEntity(ProtocolModel):
    entity: EntityRef = F("Entity involved in the hypothesis.")
    role: EntityRole = F("Role of the entity in the hypothesis.")


class HypothesisPayload(ProtocolModel):
    """A suspect: a candidate root cause with its supporting and contradicting evidence."""

    hypothesis_type: str = F("Hypothesis type (hypothesis_types.yaml), a fault or 'normal'.")
    entities: tuple[HypothesisEntity, ...] = F("Affected entities with roles.")
    local_confidence: float = F(
        "Proposer's own confidence, before correlation.", "ratio", ge=0, le=1
    )
    confidence_method: str = F("Key of the documented method that produced local_confidence.")
    supporting_clue_ids: tuple[str, ...] = F("msg_ids of CLUEs that support it.", default=())
    contradicting_clue_ids: tuple[str, ...] = F("msg_ids of CLUEs that contradict it.", default=())

    @field_validator("hypothesis_type")
    @classmethod
    def _known(cls, v: str) -> str:
        h = get_vocabulary().hypothesis_types.get(v)
        if h is None:
            raise ValueError(f"unknown hypothesis_type {v!r}")
        if v == "insufficient_evidence":
            raise ValueError(
                "insufficient_evidence is a verdict outcome, not a proposable hypothesis"
            )
        return v


class StancePayload(ProtocolModel):
    """SUPPORT or CONTRADICT: one agent's evidence bearing on another agent's post."""

    target_msg_id: str = F("msg_id of the CLUE or HYPOTHESIS being supported/contradicted.")
    clue_ids: tuple[str, ...] = F("The sender's own CLUEs that justify the stance.", min_length=1)
    strength: float = F("How strongly the evidence bears on the target.", "ratio", ge=0, le=1)
    reason_code: str = F("Machine-readable reason, e.g. 'corroborates', 'transport_healthy'.")
    note: str = F("Short human-readable explanation.", default="")


# ----------------------------------------------------------------------------- coordination
class RequestPayload(ProtocolModel):
    """Directed query for targeted evidence, routed by capability."""

    capability: str = F(
        "Requested capability: 'metric:<metric>' or 'analysis:<name>'.",
        pattern=r"^(metric|analysis):[a-z_]+$",
    )
    entity_ids: tuple[str, ...] = F("Entities to evaluate (empty = all relevant).", default=())
    params: dict[str, Scalar] = F("Capability-specific parameters.", default={})
    reason: str = F("Why the evidence is needed (e.g. 'discriminate link_congestion vs ...').")

    @field_validator("capability")
    @classmethod
    def _metric_known(cls, v: str) -> str:
        kind, name = v.split(":", 1)
        if kind == "metric" and name not in get_vocabulary().metrics:
            raise ValueError(f"unknown metric in capability {v!r}")
        return v


class ResponseStatus(StrEnum):
    OK = "ok"
    NO_DATA = "no_data"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class ResponsePayload(ProtocolModel):
    request_msg_id: str = F("msg_id of the REQUEST answered.")
    status: ResponseStatus = F("Outcome of the request.")
    result_msg_ids: tuple[str, ...] = F("msg_ids of CLUEs/HYPOTHESES posted in answer.", default=())
    detail: str = F("Explanation, especially for non-ok status.", default="")


class ErrorPayload(ProtocolModel):
    code: ErrorCode = F("Typed error code.")
    severity: Severity = F("Impact of the error on the run.")
    message: str = F("Human-readable description.")
    related_msg_id: str | None = F("Message the error concerns, if any.", default=None)
    source: SourceRef | None = F("Input location the error concerns, if any.", default=None)
    context: dict[str, Scalar] = F("Structured details (field, value, expected, ...).", default={})


class AckStatus(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class AckPayload(ProtocolModel):
    acked_msg_id: str = F("msg_id being acknowledged.")
    status: AckStatus = F("Whether the board/recipient accepted it.")
    reason: str = F("Reason for duplicate/rejected.", default="")


class CapabilityPayload(ProtocolModel):
    card: CapabilityCard = F("The sender's capability card.")


# ----------------------------------------------------------------------------- outcomes
class RankedHypothesis(ProtocolModel):
    hypothesis_type: str = F("Hypothesis type.")
    entities: tuple[HypothesisEntity, ...] = F("Entities of the (merged) hypothesis.")
    hypothesis_msg_ids: tuple[str, ...] = F("HYPOTHESIS messages merged into this candidate.")
    score: float = F("Raw evidence score (docs/SCORING.md).")
    confidence: float = F("Calibrated confidence.", "ratio", ge=0, le=1)


class VerdictPayload(ProtocolModel):
    decision: Decision = F("Outcome of correlation / courtroom.")
    hypothesis_type: str | None = F("Winning hypothesis type, null unless diagnosed.", default=None)
    entities: tuple[HypothesisEntity, ...] = F("Entities of the winning hypothesis.", default=())
    confidence: float = F("Calibrated confidence in the decision.", "ratio", ge=0, le=1)
    confidence_category: str = F("Category from config (e.g. high/medium/low).")
    ranking: tuple[RankedHypothesis, ...] = F("All candidates, best first.", default=())
    method: str = F("'correlation' or 'courtroom'.")
    missing_evidence: tuple[str, ...] = F("Data that would resolve an abstention.", default=())
    rationale: tuple[str, ...] = F("Decision-rule codes that fired, in order.", default=())


class ReportPayload(ProtocolModel):
    report: Report = F("The unified diagnostic report (A7 schema + extensions).")
