"""Bridge for an external agent (e.g. an MCP client) that joins a run with its own card.

The external agent supplies a capability card and messages in protocol 1.0 ("lite") or 2.0.
The bridge upgrades them through the version adapters, re-issues them on the board under the
external agent's id (for this incident, with deterministic ids) in its first turn, and from
then on behaves like any other agent: its posts are validated, routed, traced and correlated.

The bridge speaks 2.0 on the board on the agent's behalf, so 2.0 is added to the card's
protocol versions; the agent's own versions are kept. Not registered: it is created per run.
"""

from __future__ import annotations

from typing import Any

from netcoop.agents.base import Agent, AgentContext
from netcoop.protocol.capability import CapabilityCard
from netcoop.protocol.common import PROTOCOL_VERSION, MessageType
from netcoop.protocol.messages import Envelope
from netcoop.protocol.versioning import upgrade

ROOT_TYPES = (MessageType.CLUE, MessageType.HYPOTHESIS, MessageType.ERROR)


class ExternalAgent(Agent):
    def __init__(
        self, card: dict[str, Any] | CapabilityCard, messages: list[dict[str, Any]]
    ) -> None:
        c = card if isinstance(card, CapabilityCard) else CapabilityCard.model_validate(card)
        versions = tuple(dict.fromkeys([*c.protocol_versions, PROTOCOL_VERSION]))
        consumes = tuple(
            dict.fromkeys([*c.consumes_types, MessageType.TOPOLOGY])
        )  # gives it a first turn
        self.card = c.model_copy(update={"protocol_versions": versions, "consumes_types": consumes})
        self.pending = [upgrade(m) for m in messages]  # raises VersionError on unusable input
        for m in self.pending:
            if m.type not in ROOT_TYPES:
                raise ValueError(
                    f"external message type {m.type.value} not accepted "
                    f"(use {[t.value for t in ROOT_TYPES]})"
                )

    def step(self, inbox: list[Envelope], ctx: AgentContext) -> None:
        for m in self.pending:
            ctx.post(m.type, m.payload)
        self.pending = []
