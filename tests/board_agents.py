"""Small test agents that exercise the board and orchestrator mechanics.

They are NOT diagnostic agents: their "logic" is the minimum needed to produce a
multi-round exchange (clue -> hypothesis -> request -> response/support), failures,
timeouts and loops. Real specialists arrive in Phase 4.
"""

from __future__ import annotations

import time

from netcoop.agents.base import Agent, AgentContext
from netcoop.protocol.capability import AgentRole, CapabilityCard
from netcoop.protocol.common import (
    ComparisonBasis,
    Direction,
    EntityRole,
    MessageType,
    Statistic,
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
)

T = MessageType


def card(agent_id: str, **kw: object) -> CapabilityCard:
    base: dict[str, object] = {
        "agent_id": agent_id,
        "version": "0.0.0-test",
        "role": AgentRole.SPECIALIST,
        "description": "test agent",
        "protocol_versions": ("2.0",),
        "consumes_types": (T.OBSERVATION,),
        "produces_types": (T.CLUE,),
    }
    base.update(kw)
    return CapabilityCard.model_validate(base)


def clue_from(obs: Envelope, ctx: AgentContext, parent: Envelope | None = None) -> Envelope:
    o = obs.payload
    assert isinstance(o, ObservationPayload)
    vals = [float(p.v) for p in o.points if not isinstance(p.v, str)]
    peak, first = max(vals), vals[0]
    return ctx.post(
        T.CLUE,
        CluePayload(
            entity=o.entity,
            metric=o.metric,
            statistic=Statistic.MAX,
            value=peak,
            unit=o.unit,
            comparison=Comparison(
                basis=ComparisonBasis.BASELINE,
                reference_value=first,
                config_key="test.first_sample",
                method="test_max_vs_first",
            ),
            direction=Direction.ABOVE if peak >= first else Direction.BELOW,
            deviation=abs(peak - first),
            deviation_unit="absolute",
            significant=peak > first,
            persistence=None,
            window=TimeWindow(start=o.points[0].t, end=o.points[-1].t),
            source_observation_ids=(obs.msg_id,),
            data_quality=o.quality.score,
        ),
        parent=parent or obs,
    )


class Detector(Agent):
    """Round 1: picks the link with the highest utilisation, posts clue + hypothesis + request."""

    card = card(
        "t-detector",
        consumes_metrics=("utilization",),
        consumes_types=(T.OBSERVATION, T.RESPONSE),
        produces_types=(T.CLUE, T.HYPOTHESIS, T.REQUEST),
        hypothesis_types=("link_congestion",),
    )

    def __init__(self, capability: str = "metric:egress_queue_drops") -> None:
        self.capability = capability
        self.responses: list[Envelope] = []

    def step(self, inbox: list[Envelope], ctx: AgentContext) -> None:
        self.responses += [m for m in inbox if m.type is T.RESPONSE]
        obs = [m for m in inbox if m.type is T.OBSERVATION]
        if not obs:
            return
        best = max(obs, key=lambda m: max(float(p.v) for p in ctx.series(m).points))
        clue = clue_from(best, ctx)
        entity = ctx.series(best).entity
        hyp = ctx.post(
            T.HYPOTHESIS,
            HypothesisPayload(
                hypothesis_type="link_congestion",
                entities=(HypothesisEntity(entity=entity, role=EntityRole.ROOT),),
                local_confidence=0.5,
                confidence_method="test",
                supporting_clue_ids=(clue.msg_id,),
            ),
            parent=clue,
        )
        topo = ctx.topology()
        upstream = (
            next((e.a for e in topo.edges if e.link_id == entity.entity_id), None) if topo else None
        )
        ctx.post(
            T.REQUEST,
            RequestPayload(
                capability=self.capability,
                entity_ids=(upstream,) if upstream else (),
                reason="corroborate congestion with upstream queue drops",
            ),
            parent=hyp,
        )


class Infra(Agent):
    """Serves queue-drop requests with a clue, a RESPONSE and a SUPPORT of the hypothesis."""

    card = card(
        "t-infra",
        consumes_metrics=("egress_queue_drops",),
        produces_types=(T.CLUE, T.RESPONSE, T.SUPPORT),
        serves=("metric:*",),
    )

    def step(self, inbox: list[Envelope], ctx: AgentContext) -> None:
        for req in (m for m in inbox if m.type is T.REQUEST):
            assert isinstance(req.payload, RequestPayload)
            clues = [
                clue_from(o, ctx, parent=req)
                for e in req.payload.entity_ids
                for o in ctx.observations(metric="egress_queue_drops", entity=e)
            ]
            ctx.post(
                T.RESPONSE,
                ResponsePayload(
                    request_msg_id=req.msg_id,
                    status=ResponseStatus.OK if clues else ResponseStatus.NO_DATA,
                    result_msg_ids=tuple(c.msg_id for c in clues),
                ),
                parent=req,
                recipient=req.sender,
            )
            if clues and req.causation_id:
                ctx.post(
                    T.SUPPORT,
                    StancePayload(
                        target_msg_id=req.causation_id,
                        clue_ids=tuple(c.msg_id for c in clues),
                        strength=0.5,
                        reason_code="corroborates",
                    ),
                    parent=req,
                )


class Crasher(Agent):
    card = card("t-crasher")

    def step(self, inbox: list[Envelope], ctx: AgentContext) -> None:
        clue_from(inbox[0], ctx)  # posted, but must be discarded because the step fails
        raise RuntimeError("simulated agent bug")


class Sleeper(Agent):
    card = card("t-sleeper")

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    def step(self, inbox: list[Envelope], ctx: AgentContext) -> None:
        time.sleep(self.seconds)
        clue_from(inbox[0], ctx)


class Looper(Agent):
    """Answers every SUPPORT from its peer with another SUPPORT: an endless ping-pong."""

    def __init__(self, agent_id: str, starts: bool) -> None:
        self.card = card(
            agent_id, consumes_types=(T.OBSERVATION, T.SUPPORT), produces_types=(T.SUPPORT,)
        )
        self.starts = starts

    def step(self, inbox: list[Envelope], ctx: AgentContext) -> None:
        targets = [m for m in inbox if m.type is T.SUPPORT]
        if self.starts and not targets and any(m.type is T.OBSERVATION for m in inbox):
            targets = [next(m for m in inbox if m.type is T.OBSERVATION)]
        for t in targets[:1]:
            ctx.post(
                T.SUPPORT,
                StancePayload(
                    target_msg_id=t.msg_id,
                    clue_ids=("clue-none",),
                    strength=0.1,
                    reason_code="ping",
                ),
                parent=t,
            )


class Flooder(Agent):
    """Posts ``n`` distinct clues in one round (to hit the per-agent budget)."""

    card = card("t-flooder")

    def __init__(self, n: int) -> None:
        self.n = n

    def step(self, inbox: list[Envelope], ctx: AgentContext) -> None:
        o = inbox[0]
        base = clue_from(o, ctx)
        for i in range(self.n):
            ctx.post(T.CLUE, base.payload.model_copy(update={"deviation": float(i + 1)}), parent=o)


class Dormant(Agent):
    """Activates only on a metric the data never contains."""

    def __init__(self, optional: bool) -> None:
        self.card = card(
            f"t-dormant-{'opt' if optional else 'req'}",
            activation_metrics=("link_capacity",),
            consumes_metrics=("link_capacity",),
            optional=optional,
        )

    def step(self, inbox: list[Envelope], ctx: AgentContext) -> None:
        raise AssertionError("must never run")


class LiteOnly(Agent):
    card = card("t-lite", protocol_versions=("1.0",))

    def step(self, inbox: list[Envelope], ctx: AgentContext) -> None:
        raise AssertionError("must never run")
