"""Agent plugin interface.

An agent is a class with a ``card`` (CapabilityCard) and a ``step`` method. Each round the
orchestrator calls ``step(inbox, ctx)`` with the new board messages the card subscribes
to plus any messages addressed to the agent. The agent reads the board through ``ctx``
and posts through ``ctx.post``; it never touches the board directly, so posts can be
validated, ordered deterministically and traced.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from netcoop.board.board import Board
from netcoop.protocol.capability import CapabilityCard
from netcoop.protocol.common import BOARD, MessageType, ProtocolModel
from netcoop.protocol.messages import Envelope, make_message
from netcoop.protocol.payloads import ObservationPayload, TopologyPayload


class AgentContext:
    """What an agent may see and do during one step."""

    def __init__(self, agent_id: str, board: Board, round_no: int, now: datetime) -> None:
        self.agent_id = agent_id
        self.incident_id = board.incident_id
        self.round = round_no
        self.now = now
        self._board = board
        self.outbox: list[Envelope] = []

    # -- reading ---------------------------------------------------------------------
    def query(self, **filters: Any) -> list[Envelope]:
        return self._board.query(**filters)

    def get(self, msg_id: str) -> Envelope | None:
        return self._board.get(msg_id) or next((m for m in self.outbox if m.msg_id == msg_id), None)

    def observations(self, metric: str | None = None, entity: str | None = None) -> list[Envelope]:
        return self._board.query(type=MessageType.OBSERVATION, metric=metric, entity=entity)

    def topology(self) -> TopologyPayload | None:
        topo = self._board.query(type=MessageType.TOPOLOGY)
        payload = topo[-1].payload if topo else None
        return payload if isinstance(payload, TopologyPayload) else None

    @staticmethod
    def series(msg: Envelope) -> ObservationPayload:
        assert isinstance(msg.payload, ObservationPayload)
        return msg.payload

    # -- writing ---------------------------------------------------------------------
    def post(
        self,
        msg_type: MessageType,
        payload: ProtocolModel,
        *,
        parent: Envelope | None = None,
        recipient: str = BOARD,
    ) -> Envelope:
        """Build a message from this agent; it is committed when the step finishes."""
        msg = make_message(
            msg_type,
            sender=self.agent_id,
            correlation_id=self.incident_id,
            payload=payload,
            timestamp=self.now,
            recipient=recipient,
            parent=parent,
        )
        self.outbox.append(msg)
        return msg


class Agent(ABC):
    """Base class for board agents. Subclasses set ``card`` and implement ``step``."""

    card: CapabilityCard

    @property
    def agent_id(self) -> str:
        return self.card.agent_id

    def start(self, ctx: AgentContext) -> None:  # noqa: B027 - optional hook
        """Called once before the first round (e.g. to read the topology)."""

    @abstractmethod
    def step(self, inbox: list[Envelope], ctx: AgentContext) -> None:
        """React to new messages; post results through ``ctx.post``."""
