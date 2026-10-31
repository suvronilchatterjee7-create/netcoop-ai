"""Post-collaboration stages: correlation (-> VERDICT) and reporting (-> REPORT).

The orchestrator depends only on the ``Correlator`` / ``Reporter`` protocols. The classes
below are deliberately minimal **provisional** implementations so the pipeline runs end to
end before Phase 5 (scoring, calibration, decision policy) and Phase 7 (full reporting)
replace them. The provisional correlator never claims a diagnosis: with no documented,
calibrated scoring method yet, the only honest outcome is ``insufficient_evidence``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

from netcoop.board.board import Board
from netcoop.protocol.capability import AgentRole, CapabilityCard
from netcoop.protocol.common import PROTOCOL_VERSION, Decision, MessageType
from netcoop.protocol.messages import Envelope
from netcoop.protocol.payloads import (
    CluePayload,
    ErrorPayload,
    HypothesisPayload,
    RankedHypothesis,
    VerdictPayload,
)
from netcoop.protocol.report import (
    EvidenceItem,
    EvidenceProvenance,
    Report,
    ReportExtensions,
    ReportStatus,
    RunManifest,
)

UNRATED = "unrated"


@dataclass
class RunInfo:
    incident_id: str
    manifest: RunManifest
    rounds: int = 0
    converged: bool = False
    failed_agents: dict[str, str] = field(default_factory=dict)  # agent_id -> reason
    inactive_agents: dict[str, bool] = field(default_factory=dict)  # agent_id -> optional?


class Correlator(Protocol):
    card: CapabilityCard

    def correlate(self, board: Board, run: RunInfo) -> VerdictPayload: ...


class Reporter(Protocol):
    card: CapabilityCard

    def report(self, board: Board, verdict: Envelope, run: RunInfo) -> Report: ...


def _card(
    agent_id: str, role: AgentRole, description: str, produces: MessageType
) -> CapabilityCard:
    return CapabilityCard(
        agent_id=agent_id,
        version="0.0.1-provisional",
        role=role,
        description=description,
        protocol_versions=(PROTOCOL_VERSION,),
        consumes_types=(
            MessageType.CLUE,
            MessageType.HYPOTHESIS,
            MessageType.SUPPORT,
            MessageType.CONTRADICT,
        ),
        produces_types=(produces,),
    )


class ProvisionalCorrelator:
    card = _card(
        "correlator",
        AgentRole.CORRELATOR,
        "Provisional: ranks hypotheses by proposer confidence and always abstains.",
        MessageType.VERDICT,
    )

    def correlate(self, board: Board, run: RunInfo) -> VerdictPayload:
        ranking = []
        for m in board.query(type=MessageType.HYPOTHESIS):
            p = m.payload
            assert isinstance(p, HypothesisPayload)
            ranking.append(
                RankedHypothesis(
                    hypothesis_type=p.hypothesis_type,
                    entities=p.entities,
                    hypothesis_msg_ids=(m.msg_id,),
                    score=p.local_confidence,
                    confidence=0.0,
                )
            )
        ranking.sort(key=lambda r: (-r.score, r.hypothesis_type, r.hypothesis_msg_ids))
        return VerdictPayload(
            decision=Decision.INSUFFICIENT_EVIDENCE,
            confidence=0.0,
            confidence_category=UNRATED,
            ranking=tuple(ranking),
            method="provisional",
            rationale=("scoring_method_not_implemented",),
            missing_evidence=() if ranking else ("specialist hypotheses",),
        )


def _interpret(c: CluePayload) -> str:
    ref = c.comparison.reference_value
    return (
        f"{c.statistic.value} {c.value} {c.unit} is {c.direction.value} "
        f"the {c.comparison.basis.value} "
        f"{ref if ref is not None else ''} "
        f"({c.deviation:.3g} {c.deviation_unit}, key {c.comparison.config_key})"
    )


class ProvisionalReporter:
    card = _card(
        "reporter",
        AgentRole.REPORTER,
        "Provisional: assembles the A7 report from the verdict, clues and errors.",
        MessageType.REPORT,
    )

    def report(self, board: Board, verdict: Envelope, run: RunInfo) -> Report:
        v = verdict.payload
        assert isinstance(v, VerdictPayload)
        status = {
            Decision.DIAGNOSED: ReportStatus.DIAGNOSED,
            Decision.INSUFFICIENT_EVIDENCE: ReportStatus.INSUFFICIENT_EVIDENCE,
            Decision.NO_FAULT_DETECTED: ReportStatus.NO_FAULT_DETECTED,
        }[v.decision]
        top_ids = v.ranking[0].hypothesis_msg_ids if v.ranking else ()
        clue_ids: list[str] = []
        for hid in top_ids:
            h = board.get(hid)
            if h is not None and isinstance(h.payload, HypothesisPayload):
                clue_ids += h.payload.supporting_clue_ids
        evidence: list[EvidenceItem] = []
        provenance: list[EvidenceProvenance] = []
        sources: list[str] = []
        for cid in dict.fromkeys(clue_ids):
            m = board.get(cid)
            if (
                m is None
                or not isinstance(m.payload, CluePayload)
                or isinstance(m.payload.value, str)
            ):
                continue
            c = m.payload
            provenance.append(
                EvidenceProvenance(
                    evidence_index=len(evidence),
                    clue_id=m.msg_id,
                    agent=m.sender,
                    entity_id=c.entity.entity_id,
                    unit=c.unit,
                    reference_value=c.comparison.reference_value,
                    config_key=c.comparison.config_key,
                    observation_ids=c.source_observation_ids,
                )
            )
            evidence.append(
                EvidenceItem(metric=c.metric, value=float(c.value), interpretation=_interpret(c))
            )
            sources.append(m.sender)
        if v.decision is Decision.DIAGNOSED and v.hypothesis_type:
            cause = f"{v.hypothesis_type} at {', '.join(e.entity.entity_id for e in v.entities)}"
        else:
            cause = "insufficient evidence to name a root cause (" + ", ".join(v.rationale) + ")"
        limitations = _limitations(board, run)
        return Report(
            incident_id=run.incident_id,
            status=status,
            suspected_root_cause=cause,
            confidence=v.confidence,
            affected_devices=tuple(dict.fromkeys(e.entity.entity_id for e in v.entities)),
            supporting_evidence=tuple(evidence),
            alternative_causes=tuple(
                f"{r.hypothesis_type} at {', '.join(e.entity.entity_id for e in r.entities)}"
                for r in v.ranking[1 if v.decision is Decision.DIAGNOSED else 0 :]
            ),
            recommended_actions=(),
            evidence_sources=tuple(dict.fromkeys(sources)),
            limitations=limitations,
            x_netcoop=ReportExtensions(
                confidence_category=v.confidence_category,
                evidence_provenance=tuple(provenance),
                missing_evidence=v.missing_evidence,
                manifest=run.manifest,
            ),
        )


def _limitations(board: Board, run: RunInfo) -> tuple[str, ...]:
    out: list[str] = []
    counts: Counter[str] = Counter()
    for m in board.query(type=MessageType.ERROR):
        e = m.payload
        assert isinstance(e, ErrorPayload)
        where = (
            f"{e.source.source}"
            + (f"[{e.source.raw_field}]" if e.source and e.source.raw_field else "")
            if e.source
            else m.sender
        )
        line = f"{e.severity.value} {e.code.value} ({where}): {e.message}"
        if line not in counts:
            out.append(line)
        counts[line] += 1
    for agent, reason in sorted(run.failed_agents.items()):
        out.append(f"agent {agent} failed ({reason}); its evidence is missing")
    for agent, optional in sorted(run.inactive_agents.items()):
        if not optional:
            out.append(f"required agent {agent} had no applicable data")
    if not run.converged:
        out.append(f"collaboration stopped at the round limit ({run.rounds}) before converging")
    return tuple(out)
