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
from netcoop.catalogue import Catalogue, get_catalogue
from netcoop.config import get_value, load_config
from netcoop.correlation.features import Candidate, explains, extract, required_satisfied
from netcoop.correlation.fit import load_model
from netcoop.correlation.model import Model, Outcome, decide
from netcoop.courtroom.courtroom import Case
from netcoop.orchestrator.stages import ProvisionalCorrelator, RunInfo
from netcoop.protocol.capability import AgentRole, CapabilityCard
from netcoop.protocol.common import PROTOCOL_VERSION, Decision, MessageType
from netcoop.protocol.payloads import RankedHypothesis, TopologyPayload, VerdictPayload
from netcoop.protocol.vocabulary import get_vocabulary

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

    def __init__(self, model: Model | None = None, *, corroboration: bool = True) -> None:
        self.corroboration = corroboration  # ablation switch, see features.extract
        self.model = model if model is not None else load_model()
        self.min_accept = float(get_value(load_config("correlation_method"), "decision.min_accept"))
        self.min_positives = int(
            get_value(load_config("courtroom"), "trigger.min_training_positives")
        )
        self.case: Case | None = None
        self.last: Outcome | None = None

    def _under_trained(self, hypothesis_type: str) -> bool:
        assert self.model is not None
        return int(self.model.tables["types"][hypothesis_type]["n_true"]) < self.min_positives

    def _open_case(self, out: Outcome, cat: Catalogue, topo: Topo) -> Case | None:
        """Near tie, or a plausible competing contender the learned model cannot judge."""
        assert self.model is not None
        live = [r for r in out.ranking if r.merged_into is None]
        if not live or (out.decision != "diagnosed" and not out.near_tie):
            return None
        top = live[0]
        for r in live[1:]:
            if out.near_tie and r is live[1]:
                reason = f"near tie between {top.candidate.key} and {r.candidate.key}"
            elif (
                self._under_trained(r.candidate.hypothesis_type)
                or self._under_trained(top.candidate.hypothesis_type)
            ) and self._contends(top.candidate, r.candidate, cat, topo):
                weak = (
                    r.candidate
                    if self._under_trained(r.candidate.hypothesis_type)
                    else top.candidate
                )
                reason = (
                    f"contender {r.candidate.key} competes with {top.candidate.key}, "
                    "and the learned model "
                    f"has fewer than {self.min_positives} true training examples of "
                    f"{weak.hypothesis_type}"
                )
            else:
                continue
            return Case(
                top.candidate, r.candidate, top.confidence, r.confidence, reason, self.model.accept
            )
        return None

    @staticmethod
    def _contends(a: Candidate, b: Candidate, cat: Catalogue, topo: Topo) -> bool:
        """b rivals a: catalogue relation, overlapping location, full required signature."""
        ha, hb = cat.hypotheses[a.hypothesis_type], cat.hypotheses[b.hypothesis_type]
        related = (
            b.hypothesis_type in ha.competes_with
            or a.hypothesis_type in hb.competes_with
            or b.hypothesis_type in ha.explains
            or a.hypothesis_type in hb.explains
        )
        if not related or not required_satisfied(b, hb):
            return False
        vocab = get_vocabulary()
        ra = topo.blast_radius(a.root, vocab.category_of(a.root_type))
        rb = topo.blast_radius(b.root, vocab.category_of(b.root_type))
        return ra.matches(b.root, None) or rb.matches(a.root, None)

    def correlate(self, board: Board, run: RunInfo) -> VerdictPayload:
        self.case = None
        if self.model is None:
            v = ProvisionalCorrelator().correlate(board, run)
            return v.model_copy(update={"rationale": ("model_not_fitted: run `netcoop fit`",)})
        cat = get_catalogue()
        cands, ctx = extract(board, cat, corroboration=self.corroboration)
        topo_msgs = board.query(type=T.TOPOLOGY)
        topo = Topo(
            topo_msgs[-1].payload
            if topo_msgs and isinstance(topo_msgs[-1].payload, TopologyPayload)
            else None
        )
        out = decide(cands, ctx, self.model, cat, lambda a, b: explains(a, b, cat, topo))
        self.last = out
        self.case = self._open_case(out, cat, topo)
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
