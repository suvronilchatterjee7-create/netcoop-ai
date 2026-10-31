"""Builders for valid protocol objects used across tests.

Values are arbitrary but valid; they are not expected outputs of any diagnosis.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from netcoop.protocol.capability import AgentRole, CapabilityCard
from netcoop.protocol.common import (
    ComparisonBasis,
    DataQuality,
    Decision,
    Direction,
    EntityRef,
    EntityRole,
    ErrorCode,
    MessageType,
    ProtocolModel,
    Severity,
    Statistic,
    TimeWindow,
)
from netcoop.protocol.messages import Envelope, make_message
from netcoop.protocol.payloads import (
    AckPayload,
    AckStatus,
    CapabilityPayload,
    CluePayload,
    Comparison,
    ErrorPayload,
    HypothesisEntity,
    HypothesisPayload,
    ObservationPayload,
    Point,
    RankedHypothesis,
    ReportPayload,
    RequestPayload,
    ResponsePayload,
    ResponseStatus,
    StancePayload,
    TopologyEdge,
    TopologyNode,
    TopologyPayload,
    VerdictPayload,
)
from netcoop.protocol.report import EvidenceItem, Report, ReportExtensions, ReportStatus

T0 = datetime(2026, 1, 1, tzinfo=UTC)
INCIDENT = "inc-test"
LINK = EntityRef(entity_id="sw-a--sw-b", entity_type="link")
SWITCH = EntityRef(entity_id="sw-b", entity_type="switch")
Q = DataQuality(score=0.9, completeness=1.0, freshness=1.0, plausibility=1.0, mapping_certainty=0.8)


def observation() -> ObservationPayload:
    return ObservationPayload(
        entity=LINK,
        metric="utilization",
        unit="percent",
        points=tuple(Point(t=T0 + timedelta(minutes=i), v=10.0 + i) for i in range(3)),
        quality=Q,
    )


def clue(obs_id: str = "observation-0") -> CluePayload:
    return CluePayload(
        entity=LINK,
        metric="utilization",
        statistic=Statistic.MEDIAN,
        value=11.0,
        unit="percent",
        comparison=Comparison(
            basis=ComparisonBasis.BASELINE,
            reference_value=5.0,
            spread=1.0,
            config_key="baselines.utilization.link",
            method="robust_z",
        ),
        direction=Direction.ABOVE,
        deviation=6.0,
        deviation_unit="robust_z",
        significant=True,
        persistence=0.5,
        window=TimeWindow(start=T0, end=T0 + timedelta(minutes=2)),
        source_observation_ids=(obs_id,),
        data_quality=0.9,
    )


def hypothesis_entity() -> HypothesisEntity:
    return HypothesisEntity(entity=LINK, role=EntityRole.ROOT)


def payloads() -> dict[MessageType, ProtocolModel]:
    card = card_for("agent-x")
    report = Report(
        incident_id=INCIDENT,
        status=ReportStatus.INSUFFICIENT_EVIDENCE,
        suspected_root_cause="undetermined",
        confidence=0.2,
        affected_devices=(),
        supporting_evidence=(
            EvidenceItem(metric="utilization", value=11.0, interpretation="above baseline"),
        ),
        alternative_causes=(),
        recommended_actions=("collect more data",),
        evidence_sources=("agent-x",),
        limitations=("test",),
        x_netcoop=ReportExtensions(confidence_category="low"),
    )
    return {
        MessageType.OBSERVATION: observation(),
        MessageType.TOPOLOGY: TopologyPayload(
            nodes=(
                TopologyNode(entity=EntityRef(entity_id="sw-a", entity_type="switch")),
                TopologyNode(entity=SWITCH),
            ),
            edges=(
                TopologyEdge(
                    link_id=LINK.entity_id, a="sw-a", b="sw-b", directed=True, capacity=1000.0
                ),
            ),
            upstream_root="sw-a",
            quality=Q,
        ),
        MessageType.CLUE: clue(),
        MessageType.HYPOTHESIS: HypothesisPayload(
            hypothesis_type="link_congestion",
            entities=(hypothesis_entity(),),
            local_confidence=0.6,
            confidence_method="test",
            supporting_clue_ids=("clue-0",),
        ),
        MessageType.SUPPORT: StancePayload(
            target_msg_id="hypothesis-0",
            clue_ids=("clue-1",),
            strength=0.5,
            reason_code="corroborates",
        ),
        MessageType.CONTRADICT: StancePayload(
            target_msg_id="hypothesis-0",
            clue_ids=("clue-2",),
            strength=0.5,
            reason_code="transport_healthy",
        ),
        MessageType.REQUEST: RequestPayload(
            capability="metric:egress_queue_drops", entity_ids=("sw-a",), reason="discriminate"
        ),
        MessageType.RESPONSE: ResponsePayload(
            request_msg_id="request-0", status=ResponseStatus.OK, result_msg_ids=("clue-3",)
        ),
        MessageType.ERROR: ErrorPayload(
            code=ErrorCode.MISSING_FIELD,
            severity=Severity.RECOVERABLE,
            message="field x missing",
            context={"field": "x"},
        ),
        MessageType.ACK: AckPayload(acked_msg_id="clue-0", status=AckStatus.ACCEPTED),
        MessageType.CAPABILITY: CapabilityPayload(card=card),
        MessageType.VERDICT: VerdictPayload(
            decision=Decision.DIAGNOSED,
            hypothesis_type="link_congestion",
            entities=(hypothesis_entity(),),
            confidence=0.7,
            confidence_category="medium",
            ranking=(
                RankedHypothesis(
                    hypothesis_type="link_congestion",
                    entities=(hypothesis_entity(),),
                    hypothesis_msg_ids=("hypothesis-0",),
                    score=2.0,
                    confidence=0.7,
                ),
            ),
            method="correlation",
        ),
        MessageType.REPORT: ReportPayload(report=report),
    }


def message(t: MessageType, parent: Envelope | None = None) -> Envelope:
    return make_message(
        t,
        sender="agent-x",
        correlation_id=INCIDENT,
        payload=payloads()[t],
        timestamp=T0,
        parent=parent,
    )


def card_for(agent_id: str, **kw: object) -> CapabilityCard:
    base: dict[str, object] = {
        "agent_id": agent_id,
        "version": "0.1.0",
        "role": AgentRole.SPECIALIST,
        "description": "test agent",
        "protocol_versions": ("1.0", "2.0"),
        "consumes_types": (MessageType.OBSERVATION,),
        "consumes_metrics": ("utilization", "egress_queue_drops"),
        "produces_types": (MessageType.CLUE, MessageType.HYPOTHESIS),
        "hypothesis_types": ("link_congestion",),
        "serves": ("metric:*",),
    }
    base.update(kw)
    return CapabilityCard.model_validate(base)
