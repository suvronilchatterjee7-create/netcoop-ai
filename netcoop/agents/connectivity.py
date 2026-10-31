"""Connectivity Analysis agent: topology, blast radius and lowest common upstream.

It analyses no metric itself. It reads every CLUE (to know where the network shows
symptoms) and every HYPOTHESIS, and judges each hypothesis' *localisation*:

* the **blast radius** of a root is the set of locations a fault there can affect (a link:
  everything below its downstream end plus the upstream device; a device: its subtree and
  attached links; a service: its own probes, from anywhere);
* the share of symptomatic locations that fall inside it decides the stance: at least
  ``support_min_fraction`` -> SUPPORT, at most ``contradict_max_fraction`` -> CONTRADICT,
  in between -> no stance;
* the **lowest common upstream** device of all symptomatic locations, and whether the
  symptoms are localised (one subtree) or widespread (common upstream is the core), are
  reported in the stance note and served as ``analysis:common_upstream`` /
  ``analysis:blast_radius`` requests.

Without a topology it says so once (MISSING_TOPOLOGY) and only judges service hypotheses,
whose blast radius does not depend on the graph.
"""

from __future__ import annotations

from netcoop.agents.base import SCORE_DIGITS, Agent, AgentContext
from netcoop.agents.registry import register_agent
from netcoop.agents.scopes import Topo
from netcoop.config import get_value, load_config
from netcoop.protocol.capability import ANY, AgentRole, CapabilityCard
from netcoop.protocol.common import PROTOCOL_VERSION, EntityRole, ErrorCode, MessageType, Severity
from netcoop.protocol.messages import Envelope
from netcoop.protocol.payloads import (
    CluePayload,
    ErrorPayload,
    HypothesisPayload,
    RequestPayload,
    ResponsePayload,
    ResponseStatus,
    StancePayload,
    TopologyPayload,
)
from netcoop.protocol.vocabulary import get_vocabulary

T = MessageType


@register_agent
class ConnectivityAgent(Agent):
    card = CapabilityCard(
        agent_id="connectivity",
        version="0.1.0",
        role=AgentRole.SPECIALIST,
        description="Connectivity Analysis agent: topology graph, blast radius, lowest common "
        "upstream "
        "device; judges whether each hypothesis' location explains where symptoms appear.",
        protocol_versions=(PROTOCOL_VERSION,),
        consumes_types=(T.TOPOLOGY, T.CLUE, T.HYPOTHESIS),
        consumes_metrics=(ANY,),
        produces_types=(T.SUPPORT, T.CONTRADICT, T.RESPONSE, T.ERROR),
        serves=("analysis:blast_radius", "analysis:common_upstream"),
    )

    def __init__(self) -> None:
        cfg = load_config("specialist")
        self.support_min = float(get_value(cfg, "connectivity.support_min_fraction"))
        self.contradict_max = float(get_value(cfg, "connectivity.contradict_max_fraction"))
        self.max_cited = int(get_value(cfg, "connectivity.max_cited_clues"))
        self.min_locations = int(get_value(cfg, "connectivity.min_locations"))
        self.vocab = get_vocabulary()
        self.topo = Topo(None)
        self.symptoms: dict[tuple[str, str | None], list[str]] = {}  # (entity, vantage) -> clue ids
        self.warned = False
        self.judged: set[str] = set()

    def start(self, ctx: AgentContext) -> None:
        self.topo = Topo(ctx.topology())

    def step(self, inbox: list[Envelope], ctx: AgentContext) -> None:
        for m in inbox:
            if m.type is T.TOPOLOGY and isinstance(m.payload, TopologyPayload):
                self.topo = Topo(m.payload)
            elif m.type is T.CLUE and isinstance(m.payload, CluePayload) and m.payload.significant:
                key = (m.payload.entity.entity_id, m.payload.observed_from)
                self.symptoms.setdefault(key, []).append(m.msg_id)
        if not self.topo.present and not self.warned and any(m.type is T.HYPOTHESIS for m in inbox):
            self.warned = True
            ctx.post(
                T.ERROR,
                ErrorPayload(
                    code=ErrorCode.MISSING_TOPOLOGY,
                    severity=Severity.WARNING,
                    message="no topology: link/device localisation cannot be checked",
                ),
            )
        for m in inbox:
            if m.type is T.HYPOTHESIS:
                self._judge(m, ctx)
            elif m.type is T.REQUEST:
                self._answer(m, ctx)

    # ------------------------------------------------------------------ analysis
    def common_upstream(self) -> tuple[str | None, set[str]]:
        nodes = {loc for (e, v) in self.symptoms if (loc := self.topo.location(e, v)) is not None}
        return self.topo.lowest_common_upstream(nodes), nodes

    def _judge(self, hyp: Envelope, ctx: AgentContext) -> None:
        p: HypothesisPayload = hyp.payload
        root = next((he.entity for he in p.entities if he.role is EntityRole.ROOT), None)
        if root is None or hyp.msg_id in self.judged or not self.symptoms:
            return
        category = self.vocab.category_of(root.entity_type)
        if category != "service" and not self.topo.present:
            return
        self.judged.add(hyp.msg_id)
        region = self.topo.blast_radius(root.entity_id, category)
        inside = {k: v for k, v in self.symptoms.items() if region.matches(*k)}
        outside = {k: v for k, v in self.symptoms.items() if k not in inside}
        frac = len(inside) / len(self.symptoms)
        lca, nodes = self.common_upstream()
        root_node = self.topo.payload.upstream_root if self.topo.payload else None
        spread = (
            "widespread" if lca is not None and lca == root_node and len(nodes) > 1 else "localised"
        )
        note = (
            f"{len(inside)}/{len(self.symptoms)} symptomatic locations inside the blast radius of "
            f"{root.entity_id}; symptoms are {spread}, lowest common upstream: {lca or 'unknown'}"
        )
        located = {self.topo.location(*k) or k[0] for k in inside}
        if frac >= self.support_min and len(located) >= self.min_locations:
            mtype, code, cited, strength = T.SUPPORT, "symptoms_within_blast_radius", inside, frac
        elif frac <= self.contradict_max:
            mtype, code, cited, strength = (
                T.CONTRADICT,
                "symptoms_outside_blast_radius",
                outside,
                1 - frac,
            )
        else:
            return
        ids = [cid for k in sorted(cited, key=lambda k: (k[0], k[1] or "")) for cid in cited[k]][
            : self.max_cited
        ]
        ctx.post(
            mtype,
            StancePayload(
                target_msg_id=hyp.msg_id,
                clue_ids=tuple(ids),
                strength=round(strength, SCORE_DIGITS),
                reason_code=code,
                note=note,
            ),
            parent=hyp,
        )

    def _answer(self, req: Envelope, ctx: AgentContext) -> None:
        p: RequestPayload = req.payload
        if p.capability == "analysis:common_upstream":
            lca, nodes = self.common_upstream()
            detail = (
                f"lowest common upstream of {len(nodes)} symptomatic locations: {lca or 'unknown'}"
            )
            status = ResponseStatus.OK if lca else ResponseStatus.NO_DATA
        elif p.capability == "analysis:blast_radius" and p.entity_ids:
            regions = [
                self.topo.blast_radius(
                    e,
                    self.vocab.category_of(
                        self.topo.node_types.get(e, "link")
                        if e in self.topo.node_types or e in self.topo.links
                        else "service"
                    ),
                )
                for e in p.entity_ids
            ]
            detail = "; ".join(
                f"{e}: {len(r.ids())} locations" for e, r in zip(p.entity_ids, regions, strict=True)
            )
            status = ResponseStatus.OK if self.topo.present else ResponseStatus.NO_DATA
        else:
            return
        ctx.post(
            T.RESPONSE,
            ResponsePayload(request_msg_id=req.msg_id, status=status, detail=detail),
            parent=req,
            recipient=req.sender,
        )
