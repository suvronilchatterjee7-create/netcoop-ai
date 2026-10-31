"""Fault Correlation agent: candidates -> calibrated ranking -> VERDICT (SCORING.md section 4).

Confidence categories are tied to the fitted operating points rather than arbitrary cuts:

* **high**   - confidence >= the fitted accept threshold (where training decisions reach the
               target precision);
* **medium** - confidence >= `decision.min_accept` (more likely right than wrong);
* **low**    - below that.

For a `no_fault_detected` verdict the same rule applies with the fitted no-fault threshold.
Without a fitted model (config/correlation.yaml missing) it abstains, saying so.
"""

from __future__ import annotations

from netcoop.agents.scopes import Topo
from netcoop.board.board import Board
from netcoop.catalogue import get_catalogue
from netcoop.config import get_value, load_config
from netcoop.correlation.features import explains, extract
from netcoop.correlation.fit import load_model
from netcoop.correlation.model import Model, Outcome, decide
from netcoop.orchestrator.stages import ProvisionalCorrelator, RunInfo
from netcoop.protocol.capability import AgentRole, CapabilityCard
from netcoop.protocol.common import PROTOCOL_VERSION, Decision, MessageType
from netcoop.protocol.payloads import RankedHypothesis, TopologyPayload, VerdictPayload

T = MessageType
METHOD = "naive_bayes_llr+platt"


def category(confidence: float, high: float, medium: float) -> str:
    return "high" if confidence >= high else "medium" if confidence >= medium else "low"


class Correlator:
    card = CapabilityCard(
        agent_id="correlator",
        version="0.1.0",
        role=AgentRole.CORRELATOR,
        description="Fault Correlation agent: recomputes every candidate's signature from all "
        "agents' clues, "
        "scores it with fitted likelihood ratios, calibrates, merges causally explained effects "
        "and decides "
        "(diagnosed / near tie / insufficient evidence / no fault).",
        protocol_versions=(PROTOCOL_VERSION,),
        consumes_types=(T.OBSERVATION, T.TOPOLOGY, T.CLUE, T.HYPOTHESIS, T.SUPPORT, T.CONTRADICT),
        consumes_metrics=("*",),
        produces_types=(T.VERDICT,),
    )

    def __init__(self, model: Model | None = None) -> None:
        self.model = model if model is not None else load_model()
        self.min_accept = float(get_value(load_config("correlation_method"), "decision.min_accept"))
        self.last: Outcome | None = None

    def correlate(self, board: Board, run: RunInfo) -> VerdictPayload:
        if self.model is None:
            v = ProvisionalCorrelator().correlate(board, run)
            return v.model_copy(update={"rationale": ("model_not_fitted: run `netcoop fit`",)})
        cat = get_catalogue()
        cands, ctx = extract(board, cat)
        topo_msgs = board.query(type=T.TOPOLOGY)
        topo = Topo(
            topo_msgs[-1].payload
            if topo_msgs and isinstance(topo_msgs[-1].payload, TopologyPayload)
            else None
        )
        out = decide(cands, ctx, self.model, cat, lambda a, b: explains(a, b, cat, topo))
        self.last = out
        high = (
            self.model.normal_accept if out.decision == "no_fault_detected" else self.model.accept
        )
        rationale = list(out.rationale)
        rationale += [
            f"merged {r.candidate.key} into {r.merged_into} (causal precedence)"
            for r in out.ranking
            if r.merged_into
        ]
        if ctx.not_applicable:
            rationale.append(
                "not applicable (no possible root in data): " + ",".join(ctx.not_applicable)
            )
        winner = out.winner
        return VerdictPayload(
            decision=Decision(out.decision),
            hypothesis_type=winner.candidate.hypothesis_type if winner else None,
            entities=winner.candidate.entities if winner else (),
            confidence=round(out.confidence, 6),
            confidence_category=category(out.confidence, high, self.min_accept),
            ranking=tuple(
                RankedHypothesis(
                    hypothesis_type=r.candidate.hypothesis_type,
                    entities=r.candidate.entities,
                    hypothesis_msg_ids=tuple(r.candidate.hypothesis_msg_ids),
                    score=round(r.score, 6),
                    confidence=round(r.confidence, 6),
                )
                for r in out.ranking
            ),
            method=METHOD,
            missing_evidence=tuple(out.missing_evidence),
            rationale=tuple(rationale),
        )
