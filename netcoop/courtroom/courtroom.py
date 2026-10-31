"""Courtroom tie-break: Prosecutor, Defense and Judge (docs/COURTROOM.md, SCORING.md section 5).

Opened by the correlator when the decision is not safely evidence-based: a near tie, or a
plausible competing contender whose fault type the learned model has (almost) never seen
true in training. Everything is rule-based and deterministic.

* **Prosecutor** argues for the correlator's top candidate A; **Defense** for contender B.
* **Discriminating evidence only.** Each side's signature element is assessed only where the
  other side does not predict the same thing (same metric, statistic kind, expectation).
  Per observation (each counted once per side):
    + an observed confirmation of a prediction the other side does not make;
    - a failed prediction (deviation predicted, none seen; or normality predicted, deviation
      seen) where the other side predicts nothing there;
  each worth the element's rubric weight x the clue's data quality.
* **Attacks:** a required element with no evidence at all (missing), and being causally
  explained away by the other hypothesis without exclusive evidence of one's own.
* **Discovery:** each side REQUESTs, by capability, the metrics of its own elements that have
  no evidence yet; specialists answer in up to `judge.max_rounds` rounds.
* **Judge:** a side wins with a lead >= `judge.win_margin`, otherwise the court defers. A win for
  the correlator's top candidate confirms it. A win for the contender becomes the verdict only
  if the calibrated model also accepts it; otherwise the honest outcome is insufficient
  evidence, with both hypotheses reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import fmean

from netcoop.agents.scopes import Region
from netcoop.agents.signature import DIRECTION, SATISFIED, assess
from netcoop.catalogue import Catalogue, Element, HypothesisSpec, get_catalogue
from netcoop.config import get_value, load_config
from netcoop.correlation.features import BoardIndex, Candidate
from netcoop.protocol.capability import AgentRole, CapabilityCard
from netcoop.protocol.common import PROTOCOL_VERSION, Decision, MessageType, Statistic
from netcoop.protocol.messages import Envelope
from netcoop.protocol.payloads import CluePayload, RequestPayload, StancePayload, VerdictPayload
from netcoop.protocol.vocabulary import get_vocabulary

T = MessageType
PROSECUTOR, DEFENSE, JUDGE = "prosecutor", "defense", "judge"


def _card(
    agent_id: str, role: AgentRole, description: str, produces: tuple[MessageType, ...]
) -> CapabilityCard:
    return CapabilityCard(
        agent_id=agent_id,
        version="0.1.0",
        role=role,
        description=description,
        protocol_versions=(PROTOCOL_VERSION,),
        consumes_types=(T.RESPONSE,),
        produces_types=produces,
    )


CARDS = (
    _card(
        PROSECUTOR,
        AgentRole.ADJUDICATOR,
        "Courtroom: argues for the correlator's top candidate.",
        (T.REQUEST, T.SUPPORT, T.CONTRADICT),
    ),
    _card(
        DEFENSE,
        AgentRole.ADJUDICATOR,
        "Courtroom: argues for the competing contender.",
        (T.REQUEST, T.SUPPORT, T.CONTRADICT),
    ),
    _card(
        JUDGE,
        AgentRole.ADJUDICATOR,
        "Courtroom: scores both cases with the documented rubric and rules.",
        (T.VERDICT,),
    ),
)


@dataclass
class Case:
    """A dispute between the correlator's top candidate (a) and a contender (b)."""

    a: Candidate
    b: Candidate
    a_confidence: float
    b_confidence: float
    reason: str
    accept: float


@dataclass
class Point:
    kind: str  # confirmed | failed | missing | explained_away
    points: float
    metric: str
    clue_ids: tuple[str, ...] = ()


@dataclass
class Brief:
    side: str
    candidate: Candidate
    points: list[Point] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(sum(p.points for p in self.points), 6)

    def summary(self) -> str:
        parts: dict[str, float] = {}
        for p in self.points:
            parts[p.kind] = parts.get(p.kind, 0.0) + p.points
        detail = (
            ", ".join(f"{k} {v:+.2f}" for k, v in sorted(parts.items()))
            or "no discriminating evidence"
        )
        return f"{self.side} for {self.candidate.key}: {self.total:+.2f} ({detail})"


def _met(e: Element, c: Envelope) -> bool:
    """Does clue ``c`` meet element ``e``'s expectation?"""
    p: CluePayload = c.payload
    deviates = p.significant and p.direction is DIRECTION[e.direction]
    return deviates if e.expect == "deviates" else not deviates


def _same_prediction(e: Element, o: Element) -> bool:
    return (
        e.metric == o.metric
        and e.expect == o.expect
        and (e.direction == "rising") == (o.direction == "rising")
        and (e.expect == "normal" or e.direction == o.direction)
    )


def _conflicting(e: Element, o: Element) -> bool:
    return (
        e.metric == o.metric
        and e.expect != o.expect
        and (e.direction == "rising") == (o.direction == "rising")
    )


class Courtroom:
    def __init__(self, catalogue: Catalogue | None = None) -> None:
        cfg = load_config("courtroom")
        self.cat = catalogue or get_catalogue()
        w = get_value(cfg, "rubric.weights")
        self.weights = {"required": float(w["required"]), "supporting": float(w["supporting"])}
        self.missing = float(get_value(cfg, "rubric.missing_required"))
        self.explained_away = float(get_value(cfg, "rubric.explained_away"))
        self.margin = float(get_value(cfg, "judge.win_margin"))
        self.max_rounds = int(get_value(cfg, "judge.max_rounds"))
        self.vocab = get_vocabulary()

    # ------------------------------------------------------------------ regions
    def _region(self, idx: BoardIndex, e: Element, root: str) -> Region:
        return idx.topo.resolve(e.scope, root, dict(idx.probes))

    def _in_scope(self, idx: BoardIndex, e: Element, root: str) -> list[Envelope]:
        region = self._region(idx, e, root)
        slope = e.direction == "rising"
        return [
            c
            for c in idx.clues.get(e.metric, ())
            if (c.payload.statistic is Statistic.SLOPE) == slope
            and region.matches(c.payload.entity.entity_id, c.payload.observed_from)
        ]

    # ------------------------------------------------------------------ discovery
    def discovery(self, case: Case, idx: BoardIndex) -> list[tuple[str, RequestPayload]]:
        out = []
        for side, cand in ((PROSECUTOR, case.a), (DEFENSE, case.b)):
            h = self.cat.hypotheses[cand.hypothesis_type]
            asked: set[str] = set()
            for e in h.signature:
                if e.metric in asked or self._in_scope(idx, e, cand.root):
                    continue
                ids = self._region(idx, e, cand.root).ids()
                if ids:
                    asked.add(e.metric)
                    out.append(
                        (
                            side,
                            RequestPayload(
                                capability=f"metric:{e.metric}",
                                entity_ids=tuple(ids),
                                reason=f"courtroom: {cand.key} predicts {e.metric} "
                                f"{e.expect} {e.direction} at {e.scope}",
                            ),
                        )
                    )
        return out

    # ------------------------------------------------------------------ briefs
    def brief(self, side: str, own: Candidate, other: Candidate, idx: BoardIndex) -> Brief:
        """Score one side's case on discriminating evidence (see module docstring)."""
        h, ho = self.cat.hypotheses[own.hypothesis_type], self.cat.hypotheses[other.hypothesis_type]
        b = Brief(side, own)
        used: set[str] = set()
        group_ok: dict[str, bool] = {}
        failures: dict[str, list[Point]] = {}
        for e in sorted(h.signature, key=lambda x: x.role != "required"):
            full = self._in_scope(idx, e, own.root)
            if not full:
                if e.role == "required" and e.expect == "deviates":
                    failures.setdefault(e.group_key, []).append(
                        Point("missing", -self.missing, e.metric)
                    )
                continue
            same = [
                self._region(idx, o, other.root) for o in ho.signature if _same_prediction(e, o)
            ]
            conflict = [
                self._region(idx, o, other.root) for o in ho.signature if _conflicting(e, o)
            ]
            diff = [
                c
                for c in full
                if not any(
                    r.matches(c.payload.entity.entity_id, c.payload.observed_from) for r in same
                )
                and not set(c.payload.source_observation_ids) & used
            ]
            shared_ok = (
                len(diff) < len(full)
                and assess(e, own.root, idx.clues, idx.topo, idx.probes).status == SATISFIED
            )
            if e.role == "required":
                group_ok[e.group_key] = group_ok.get(e.group_key, False) or shared_ok
            if not diff:
                continue
            if e.expect == "normal" and not any(
                r.matches(c.payload.entity.entity_id, c.payload.observed_from)
                for c in diff
                for r in conflict
            ):
                continue  # 'stays normal' only discriminates against a side predicting a deviation
            good = [c for c in diff if _met(e, c)]
            bad = [c for c in diff if c not in good]
            ok = (
                len(good) / len(diff) >= e.quorum
                if e.quorum is not None
                else bool(good)
                if e.expect == "deviates"
                else not bad
            )
            clues = good if ok else bad
            for c in clues:
                used |= set(c.payload.source_observation_ids)
            w = self.weights[e.role] * fmean(c.payload.data_quality for c in clues)
            point = Point(
                "confirmed" if ok else "failed",
                w if ok else -w,
                e.metric,
                tuple(c.msg_id for c in clues),
            )
            if ok:
                b.points.append(point)
                if e.role == "required":
                    group_ok[e.group_key] = True
            elif e.role == "required" and e.group:
                failures.setdefault(e.group_key, []).append(point)
            else:
                b.points.append(point)
        for key, pts in sorted(failures.items()):
            if not group_ok.get(key, False):
                b.points.append(min(pts, key=lambda p: p.points))  # a failed group is charged once
        if not any(p.points > 0 for p in b.points) and self._explains(other, own, ho, idx):
            b.points.append(Point("explained_away", -self.explained_away, ""))
        return b

    def _explains(
        self, cause: Candidate, effect: Candidate, hc: HypothesisSpec, idx: BoardIndex
    ) -> bool:
        if effect.hypothesis_type not in hc.explains:
            return False
        region = idx.topo.blast_radius(cause.root, self.vocab.category_of(cause.root_type))
        return region.matches(effect.root, None) or effect.root in region.vantages

    # ------------------------------------------------------------------ ruling
    def arguments(
        self, prosecution: Brief, defense: Brief
    ) -> list[tuple[str, MessageType, Candidate, StancePayload]]:
        """Stance messages: each side supports its own case and attacks the other's."""
        out = []
        for brief, opp, side in (
            (prosecution, defense, PROSECUTOR),
            (defense, prosecution, DEFENSE),
        ):
            pos = [i for p in brief.points if p.points > 0 for i in p.clue_ids]
            neg = [i for p in opp.points if p.points < 0 for i in p.clue_ids]
            if pos:
                out.append(
                    (
                        side,
                        T.SUPPORT,
                        brief.candidate,
                        StancePayload(
                            target_msg_id=brief.candidate.hypothesis_msg_ids[0],
                            clue_ids=tuple(dict.fromkeys(pos)),
                            strength=min(
                                1.0,
                                max(0.0, brief.total / (abs(brief.total) + abs(opp.total) or 1.0)),
                            ),
                            reason_code="discriminating_evidence",
                            note=brief.summary(),
                        ),
                    )
                )
            if neg:
                out.append(
                    (
                        side,
                        T.CONTRADICT,
                        opp.candidate,
                        StancePayload(
                            target_msg_id=opp.candidate.hypothesis_msg_ids[0],
                            clue_ids=tuple(dict.fromkeys(neg)),
                            strength=min(
                                1.0,
                                sum(-p.points for p in opp.points if p.points < 0)
                                / (sum(abs(p.points) for p in opp.points) or 1.0),
                            ),
                            reason_code="failed_predictions",
                            note="; ".join(
                                f"{p.kind} {p.metric}" for p in opp.points if p.points < 0
                            ),
                        ),
                    )
                )
        return out

    def rule(
        self,
        case: Case,
        prosecution: Brief,
        defense: Brief,
        preliminary: VerdictPayload,
        rounds: int,
    ) -> VerdictPayload:
        lead = prosecution.total - defense.total
        rationale = [
            f"courtroom opened: {case.reason}",
            f"contenders: {case.a.key} vs {case.b.key}",
            prosecution.summary(),
            defense.summary(),
            f"lead {lead:+.2f}, required margin {self.margin:.2f}, rounds {rounds}",
        ]
        decision, winner, conf = (
            Decision.INSUFFICIENT_EVIDENCE,
            None,
            max(case.a_confidence, case.b_confidence),
        )
        if lead >= self.margin:
            decision, winner, conf = Decision.DIAGNOSED, case.a, case.a_confidence
            rationale.append(f"ruling: {case.a.key} confirmed")
        elif -lead >= self.margin:
            if case.b_confidence >= case.accept:
                decision, winner, conf = Decision.DIAGNOSED, case.b, case.b_confidence
                rationale.append(
                    f"ruling: {case.b.key} preferred and accepted by the calibrated model"
                )
            else:
                rationale.append(
                    f"ruling: evidence favours {case.b.key}, but the calibrated model gives it "
                    f"{case.b_confidence:.2f} < {case.accept:.2f} (never trained on it): deferred"
                )
        else:
            rationale.append(
                "ruling: neither case clearly ahead: deferred, both hypotheses reported"
            )
        if decision is Decision.DIAGNOSED and winner is not None:
            category = preliminary.confidence_category if winner is case.a else "medium"
            return preliminary.model_copy(
                update={
                    "decision": decision,
                    "hypothesis_type": winner.hypothesis_type,
                    "entities": winner.entities,
                    "confidence": round(conf, 6),
                    "confidence_category": category,
                    "method": "courtroom",
                    "rationale": tuple(rationale),
                    "missing_evidence": (),
                }
            )
        return preliminary.model_copy(
            update={
                "decision": decision,
                "hypothesis_type": None,
                "entities": (),
                "confidence": round(conf, 6),
                "confidence_category": "low",
                "method": "courtroom",
                "rationale": tuple(rationale),
                "missing_evidence": tuple(
                    dict.fromkeys(
                        [
                            *preliminary.missing_evidence,
                            f"evidence that discriminates {case.a.key} from {case.b.key}",
                        ]
                    )
                ),
            }
        )
