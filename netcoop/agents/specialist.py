"""Generic specialist engine; the specialists themselves are data (config/catalogue/agents.yaml).

Per round a specialist:

1. turns every new OBSERVATION of its metrics into CLUEs (level evidence, plus trend evidence
   for counter metrics) using the shared detection library; non-significant clues are posted
   too, as explicit negative evidence;
2. proposes HYPOTHESES from the catalogue: for each fault whose required signature it can
   observe, candidate roots are found by inverting the scopes of its significant clues; a
   candidate is proposed when every required group it can assess is satisfied;
3. asks other agents, by capability, for signature metrics it cannot observe (REQUEST);
4. SUPPORTS or CONTRADICTS other agents' hypotheses with its own clues on the signature
   elements it can assess;
5. answers REQUESTs for its metrics with the matching clues (RESPONSE).

No metric names, thresholds, device ids or fault-specific branches appear here: everything
comes from the card, the catalogue, the detection config and the data.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import fmean

from netcoop.agents.base import SCORE_DIGITS, Agent, AgentContext
from netcoop.agents.registry import register_agent
from netcoop.agents.scopes import Topo
from netcoop.agents.signature import Assessment, assess
from netcoop.catalogue import (
    Element,
    HypothesisSpec,
    SpecialistSpec,
    get_catalogue,
    load_specialists,
)
from netcoop.config import get_value, load_config
from netcoop.detection import Detector, Finding
from netcoop.protocol.capability import AgentRole, CapabilityCard
from netcoop.protocol.common import (
    PROTOCOL_VERSION,
    Direction,
    EntityRef,
    EntityRole,
    MessageType,
    TimeWindow,
)
from netcoop.protocol.messages import Envelope
from netcoop.protocol.payloads import (
    CluePayload,
    Comparison,
    HypothesisEntity,
    HypothesisPayload,
    ObservationPayload,
    RequestPayload,
    ResponsePayload,
    ResponseStatus,
    StancePayload,
    TopologyPayload,
)
from netcoop.protocol.vocabulary import get_vocabulary

T = MessageType
_DIRECTION = {
    "above": Direction.ABOVE,
    "below": Direction.BELOW,
    "changed": Direction.CHANGED,
    "rising": Direction.ABOVE,
}
LOCAL_CONFIDENCE_METHOD = "signature_weight_ratio_x_quality"


def proposable(spec_metrics: set[str], h: HypothesisSpec) -> bool:
    """An agent may propose ``h`` if it can observe at least one element of every required group."""
    groups: dict[str, set[str]] = defaultdict(set)
    for e in h.required:
        groups[e.group_key].add(e.metric)
    return all(metrics & spec_metrics for metrics in groups.values())


def build_card(spec: SpecialistSpec) -> CapabilityCard:
    cat = get_catalogue()
    hyps = tuple(h for h, hs in cat.hypotheses.items() if proposable(set(spec.metrics), hs))
    return CapabilityCard(
        agent_id=spec.id,
        version="0.1.0",
        role=AgentRole.SPECIALIST,
        description=spec.description,
        protocol_versions=(PROTOCOL_VERSION,),
        consumes_types=(T.TOPOLOGY, T.OBSERVATION, T.HYPOTHESIS, T.RESPONSE),
        consumes_metrics=spec.metrics,
        produces_types=(T.CLUE, T.HYPOTHESIS, T.SUPPORT, T.CONTRADICT, T.REQUEST, T.RESPONSE),
        hypothesis_types=hyps,
        serves=("metric:*",),
        optional=spec.optional,
        activation_metrics=spec.metrics,
    )


class SpecialistAgent(Agent):
    spec: SpecialistSpec

    def __init__(self) -> None:
        self.detector = Detector()
        self.vocab = get_vocabulary()
        self.catalogue = get_catalogue()
        w = get_value(load_config("specialist"), "local_confidence.weights")
        self.weights = {"required": float(w["required"]), "supporting": float(w["supporting"])}
        self.metrics = set(self.card.consumes_metrics)
        self.topo = Topo(None)
        self.clues: dict[str, list[Envelope]] = defaultdict(list)  # metric -> my clues
        self.entity_types: dict[str, str] = {}
        self.probes: dict[str, set[str]] = defaultdict(set)  # service -> vantages
        self.proposed: set[tuple[str, str]] = set()
        self.stanced: set[str] = set()
        self.foreign_metrics = {
            m for h in self.card.hypothesis_types for m in self.catalogue.hypotheses[h].metrics()
        } - self.metrics

    # ------------------------------------------------------------------ main step
    def start(self, ctx: AgentContext) -> None:
        topo = ctx.topology()
        self.topo = Topo(topo)
        for n in topo.nodes if topo else ():
            self.entity_types[n.entity.entity_id] = n.entity.entity_type
        for lid in self.topo.links:
            self.entity_types[lid] = "link"
        # Where each service is probed from (any metric): needed for scopes like probe_paths
        # even by agents that do not analyse the service metrics themselves.
        for m in ctx.query(type=T.OBSERVATION):
            o: ObservationPayload = m.payload
            if o.observed_from is not None:
                self.probes[o.entity.entity_id].add(o.observed_from)

    def step(self, inbox: list[Envelope], ctx: AgentContext) -> None:
        new_obs = False
        for m in inbox:
            if m.type is T.TOPOLOGY and isinstance(m.payload, TopologyPayload):
                self.topo = Topo(m.payload)
            elif m.type is T.OBSERVATION and isinstance(m.payload, ObservationPayload):
                self._observe(m, ctx)
                new_obs = True
        if new_obs:
            self._propose(ctx)
        for m in inbox:
            if m.type is T.HYPOTHESIS and m.sender != self.agent_id:
                self._stance(m, ctx)
            elif m.type is T.REQUEST:
                self._answer(m, ctx)

    # ------------------------------------------------------------------ evidence
    def _observe(self, obs: Envelope, ctx: AgentContext) -> None:
        o: ObservationPayload = obs.payload
        self.entity_types[o.entity.entity_id] = o.entity.entity_type
        if o.observed_from is not None:
            self.probes[o.entity.entity_id].add(o.observed_from)
        for finding in (self.detector.evaluate(o), self.detector.trend(o)):
            if finding is not None:
                self.clues[o.metric].append(
                    ctx.post(T.CLUE, self._clue(o, obs, finding), parent=obs)
                )

    @staticmethod
    def _clue(o: ObservationPayload, obs: Envelope, f: Finding) -> CluePayload:
        return CluePayload(
            entity=o.entity,
            metric=o.metric,
            statistic=f.statistic,
            value=f.value,
            unit=f.unit,
            comparison=Comparison(
                basis=f.basis,
                reference_value=f.reference,
                spread=f.spread,
                config_key=f.config_key,
                method=f.method,
            ),
            direction=f.direction,
            deviation=f.deviation,
            deviation_unit=f.deviation_unit,
            significant=f.significant,
            persistence=f.persistence,
            window=TimeWindow(start=o.points[0].t, end=o.points[-1].t),
            observed_from=o.observed_from,
            source_observation_ids=(obs.msg_id,),
            data_quality=o.quality.score,
        )

    # ------------------------------------------------------------------ signature assessment
    def assess(self, e: Element, root: str) -> Assessment:
        return assess(e, root, self.clues, self.topo, self.probes)

    def _evaluate(self, h: HypothesisSpec, root: str) -> tuple[dict[Element, Assessment], float]:
        results = {e: self.assess(e, root) for e in h.signature if e.metric in self.metrics}
        observed = {e: a for e, a in results.items() if a.status != "unknown"}
        if not observed:
            return results, 0.0
        total = sum(self.weights[e.role] for e in observed)
        sat = sum(self.weights[e.role] for e, a in observed.items() if a.status == "satisfied")
        used = [
            c.payload.data_quality
            for a in observed.values()
            if a.status == "satisfied"
            for c in a.good
        ]
        return results, (sat / total) * (fmean(used) if used else 0.0)

    def _required_ok(self, h: HypothesisSpec, results: dict[Element, Assessment]) -> bool:
        groups: dict[str, list[Assessment]] = defaultdict(list)
        for e in h.required:
            if e in results:
                groups[e.group_key].append(results[e])
        return bool(groups) and all(
            any(a.status == "satisfied" for a in g) for g in groups.values()
        )

    # ------------------------------------------------------------------ proposing
    def _root_type(self, root: str) -> str | None:
        return self.entity_types.get(root)

    def _propose(self, ctx: AgentContext) -> None:
        for hid in self.card.hypothesis_types:
            h = self.catalogue.hypotheses[hid]
            roots: set[str] = set()
            for e in h.required:
                if e.metric not in self.metrics:
                    continue
                for c in self.clues.get(e.metric, []):
                    p: CluePayload = c.payload
                    if p.significant:
                        roots |= self.topo.invert(e.scope, p.entity.entity_id, p.observed_from)
            for root in sorted(roots):
                rtype = self._root_type(root)
                if rtype is None or not h.locus.admits(root, rtype) or (hid, root) in self.proposed:
                    continue
                results, confidence = self._evaluate(h, root)
                if not self._required_ok(h, results):
                    continue
                self.proposed.add((hid, root))
                self._post_hypothesis(h, root, rtype, results, confidence, ctx)

    def _post_hypothesis(
        self,
        h: HypothesisSpec,
        root: str,
        rtype: str,
        results: dict[Element, Assessment],
        confidence: float,
        ctx: AgentContext,
    ) -> None:
        support = [c for a in results.values() if a.status == "satisfied" for c in a.good]
        against = [c for a in results.values() if a.status == "violated" for c in a.bad]
        entities = [
            HypothesisEntity(
                entity=EntityRef(entity_id=root, entity_type=rtype), role=EntityRole.ROOT
            )
        ]
        seen = {root}
        for c in support:
            ent = c.payload.entity
            if ent.entity_id not in seen:
                seen.add(ent.entity_id)
                entities.append(HypothesisEntity(entity=ent, role=EntityRole.SYMPTOM))
        anchor = next(
            c
            for e, a in results.items()
            if e.role == "required" and a.status == "satisfied"
            for c in a.good
        )
        hyp = ctx.post(
            T.HYPOTHESIS,
            HypothesisPayload(
                hypothesis_type=h.id,
                entities=tuple(entities),
                local_confidence=round(confidence, SCORE_DIGITS),
                confidence_method=LOCAL_CONFIDENCE_METHOD,
                supporting_clue_ids=tuple(dict.fromkeys(c.msg_id for c in support)),
                contradicting_clue_ids=tuple(dict.fromkeys(c.msg_id for c in against)),
            ),
            parent=anchor,
        )
        self._request_missing(h, root, hyp, ctx)

    def _request_missing(
        self, h: HypothesisSpec, root: str, hyp: Envelope, ctx: AgentContext
    ) -> None:
        asked: set[str] = set()
        for e in h.signature:
            if e.metric in self.metrics or e.metric in asked:
                continue
            region = self.topo.resolve(e.scope, root, self.probes)
            ids = region.ids()
            if not ids:
                continue
            asked.add(e.metric)
            ctx.post(
                T.REQUEST,
                RequestPayload(
                    capability=f"metric:{e.metric}",
                    entity_ids=tuple(ids),
                    reason=f"{h.id} at {root}: signature element {e.metric} "
                    f"({e.expect} {e.direction}, {e.scope})",
                ),
                parent=hyp,
            )

    # ------------------------------------------------------------------ reacting
    def _stance(self, hyp: Envelope, ctx: AgentContext) -> None:
        p: HypothesisPayload = hyp.payload
        h = self.catalogue.hypotheses.get(p.hypothesis_type)
        root = next((he.entity.entity_id for he in p.entities if he.role is EntityRole.ROOT), None)
        if h is None or root is None or hyp.msg_id in self.stanced:
            return
        self.stanced.add(hyp.msg_id)
        results = {e: self.assess(e, root) for e in h.signature if e.metric in self.metrics}
        observed = {e: a for e, a in results.items() if a.status != "unknown"}
        if not observed:
            return
        total = sum(self.weights[e.role] for e in observed)
        for status, mtype, code in (
            ("satisfied", T.SUPPORT, "signature_match"),
            ("violated", T.CONTRADICT, "signature_violation"),
        ):
            elems = {e: a for e, a in observed.items() if a.status == status}
            if not elems:
                continue
            clues = [
                c for a in elems.values() for c in (a.good if status == "satisfied" else a.bad)
            ]
            ctx.post(
                mtype,
                StancePayload(
                    target_msg_id=hyp.msg_id,
                    clue_ids=tuple(dict.fromkeys(c.msg_id for c in clues)),
                    strength=round(sum(self.weights[e.role] for e in elems) / total, SCORE_DIGITS),
                    reason_code=code,
                    note="; ".join(
                        f"{e.metric} {e.expect} {e.direction} @ {e.scope}" for e in elems
                    ),
                ),
                parent=hyp,
            )

    def _answer(self, req: Envelope, ctx: AgentContext) -> None:
        p: RequestPayload = req.payload
        kind, _, metric = p.capability.partition(":")
        if kind != "metric" or metric not in self.metrics:
            return
        wanted = set(p.entity_ids)
        clues = [
            c
            for c in self.clues.get(metric, [])
            if not wanted
            or c.payload.entity.entity_id in wanted
            or c.payload.observed_from in wanted
        ]
        ctx.post(
            T.RESPONSE,
            ResponsePayload(
                request_msg_id=req.msg_id,
                status=ResponseStatus.OK if clues else ResponseStatus.NO_DATA,
                result_msg_ids=tuple(c.msg_id for c in clues),
                detail=f"{len(clues)} clue(s) for {metric}; "
                f"{sum(c.payload.significant for c in clues)} significant",
            ),
            parent=req,
            recipient=req.sender,
        )


def _make_specialist(spec: SpecialistSpec) -> type[SpecialistAgent]:
    cls = type(
        f"{spec.id.title().replace('_', '')}Agent",
        (SpecialistAgent,),
        {
            "spec": spec,
            "card": build_card(spec),
            "__doc__": spec.description,
            "__module__": __name__,
        },
    )
    return cls


SPECIALISTS: dict[str, type[SpecialistAgent]] = {}
for _spec in load_specialists():
    SPECIALISTS[_spec.id] = register_agent(_make_specialist(_spec))  # type: ignore[assignment]
