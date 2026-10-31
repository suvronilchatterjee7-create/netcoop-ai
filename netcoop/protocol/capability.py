"""Capability cards: what an agent consumes, produces and can be asked for.

The orchestrator routes messages and REQUESTs by matching cards, never by hard-coded
agent wiring. A card is also exchanged on the wire as a CAPABILITY message, so an
external agent (e.g. via MCP) can join by announcing one.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import field_validator, model_validator

from netcoop.protocol.common import F, MessageType, ProtocolModel
from netcoop.protocol.vocabulary import get_vocabulary

ANY = "*"


class AgentRole(StrEnum):
    TRANSLATOR = "translator"
    SPECIALIST = "specialist"
    CORRELATOR = "correlator"
    ADJUDICATOR = "adjudicator"
    REPORTER = "reporter"
    EXTERNAL = "external"


class CapabilityCard(ProtocolModel):
    agent_id: str = F(
        "Unique agent identifier; used as `sender`/`recipient`.", pattern=r"^[a-z][a-z0-9_.-]*$"
    )
    version: str = F("Agent implementation version (semver).")
    role: AgentRole = F("Kind of agent.")
    description: str = F("What the agent is responsible for.")
    protocol_versions: tuple[str, ...] = F("Protocol versions the agent can speak.", min_length=1)
    consumes_types: tuple[MessageType, ...] = F("Message types the agent wants delivered.")
    consumes_metrics: tuple[str, ...] = F("Canonical metrics it analyses ('*' = all).", default=())
    produces_types: tuple[MessageType, ...] = F("Message types the agent may emit.")
    hypothesis_types: tuple[str, ...] = F("Hypothesis types it may propose.", default=())
    serves: tuple[str, ...] = F(
        "REQUEST capabilities it answers: 'metric:<name>', 'analysis:<name>', or 'metric:*' "
        "(any metric in consumes_metrics).",
        default=(),
    )
    optional: bool = F("If true, absence or inactivity does not lower confidence.", default=False)
    activation_metrics: tuple[str, ...] = F(
        "Agent runs only if at least one of these metrics is observed (empty = always).", default=()
    )

    @model_validator(mode="after")
    def _check_vocab(self) -> CapabilityCard:
        vocab = get_vocabulary()
        for m in (*self.consumes_metrics, *self.activation_metrics):
            if m != ANY and m not in vocab.metrics:
                raise ValueError(f"unknown metric {m!r}")
        for h in self.hypothesis_types:
            if h not in vocab.hypothesis_types:
                raise ValueError(f"unknown hypothesis type {h!r}")
        if self.hypothesis_types and MessageType.HYPOTHESIS not in self.produces_types:
            raise ValueError("card lists hypothesis_types but does not produce HYPOTHESIS")
        return self

    @field_validator("serves")
    @classmethod
    def _serves_format(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        for cap in v:
            kind, _, name = cap.partition(":")
            if kind not in ("metric", "analysis") or not name:
                raise ValueError(f"bad capability {cap!r}")
        return v

    # -- routing --------------------------------------------------------------------
    def wants(self, msg_type: MessageType, metric: str | None = None) -> bool:
        """Should a message of this type (about this metric, if any) be delivered?"""
        if msg_type not in self.consumes_types:
            return False
        if metric is None or not self.consumes_metrics:
            return True
        return ANY in self.consumes_metrics or metric in self.consumes_metrics

    def can_serve(self, capability: str) -> bool:
        if capability in self.serves:
            return True
        kind, _, name = capability.partition(":")
        # 'metric:*' = re-evaluate any metric this agent consumes.
        if kind == "metric" and f"metric:{ANY}" in self.serves:
            return ANY in self.consumes_metrics or name in self.consumes_metrics
        return False

    def is_active(self, observed_metrics: set[str]) -> bool:
        return not self.activation_metrics or bool(observed_metrics & set(self.activation_metrics))
