"""The netcoop message envelope and the typed message union.

A message is ``Envelope`` fields + ``type`` + a payload whose model is fixed by ``type``.
Parsing uses a discriminated union on ``type``, so a payload that does not match its type
is rejected. ``make_message`` builds messages with deterministic content-hash ids.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, Field, TypeAdapter, field_validator

from netcoop.config import get_value, load_config
from netcoop.protocol.common import (
    BOARD,
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    F,
    MessageType,
    ProtocolModel,
)
from netcoop.protocol.payloads import (
    AckPayload,
    CapabilityPayload,
    CluePayload,
    ErrorPayload,
    HypothesisPayload,
    ObservationPayload,
    ReportPayload,
    RequestPayload,
    ResponsePayload,
    StancePayload,
    TopologyPayload,
    VerdictPayload,
)
from netcoop.protocol.vocabulary import get_vocabulary


class Envelope(ProtocolModel):
    """Fields common to every message; `type` and `payload` are added per message type."""

    protocol: Literal["netcoop"] = F("Protocol name; always 'netcoop'.", default=PROTOCOL_NAME)
    protocol_version: Literal["2.0"] = F(
        "Wire-format version of this message.", default=PROTOCOL_VERSION
    )
    schema_version: str = F("Controlled-vocabulary version the payload's terms refer to.")
    msg_id: str = F("Unique message id; content hash when built by make_message.", min_length=1)
    correlation_id: str = F(
        "Incident id shared by every message of one diagnosis run.", min_length=1
    )
    causation_id: str | None = F(
        "msg_id of the message that caused this one (null = root).", default=None
    )
    depth: int = F("Causation depth: 0 for roots, parent depth + 1 otherwise.", ge=0, default=0)
    sender: str = F("agent_id of the sender.", min_length=1)
    recipient: str = F("agent_id of the recipient, or 'board' for a shared post.", default=BOARD)
    timestamp: AwareDatetime = F("Creation time, ISO-8601 UTC (excluded from msg_id).")
    adaptations: tuple[str, ...] = F(
        "Version conversions applied, e.g. '1.0->2.0', and any lossy fields.", default=()
    )

    @field_validator("schema_version")
    @classmethod
    def _known_vocab(cls, v: str) -> str:
        if v != get_vocabulary().version:
            raise ValueError(
                f"schema_version {v!r} does not match vocabulary {get_vocabulary().version!r}"
            )
        return v


class ObservationMessage(Envelope):
    """Canonical telemetry series (Translator output)."""

    type: Literal[MessageType.OBSERVATION] = F("Message type.", default=MessageType.OBSERVATION)
    payload: ObservationPayload = F("Canonical telemetry series.")


class TopologyMessage(Envelope):
    """Network graph from the input data."""

    type: Literal[MessageType.TOPOLOGY] = F("Message type.", default=MessageType.TOPOLOGY)
    payload: TopologyPayload = F("Network graph.")


class ClueMessage(Envelope):
    """A piece of evidence."""

    type: Literal[MessageType.CLUE] = F("Message type.", default=MessageType.CLUE)
    payload: CluePayload = F("Evidence.")


class HypothesisMessage(Envelope):
    """A candidate root cause."""

    type: Literal[MessageType.HYPOTHESIS] = F("Message type.", default=MessageType.HYPOTHESIS)
    payload: HypothesisPayload = F("Candidate root cause.")


class SupportMessage(Envelope):
    """Evidence supporting another agent's post."""

    type: Literal[MessageType.SUPPORT] = F("Message type.", default=MessageType.SUPPORT)
    payload: StancePayload = F("Supporting stance.")


class ContradictMessage(Envelope):
    """Evidence contradicting another agent's post."""

    type: Literal[MessageType.CONTRADICT] = F("Message type.", default=MessageType.CONTRADICT)
    payload: StancePayload = F("Contradicting stance.")


class RequestMessage(Envelope):
    """Directed evidence query, routed by capability."""

    type: Literal[MessageType.REQUEST] = F("Message type.", default=MessageType.REQUEST)
    payload: RequestPayload = F("Evidence query.")


class ResponseMessage(Envelope):
    """Answer to a REQUEST."""

    type: Literal[MessageType.RESPONSE] = F("Message type.", default=MessageType.RESPONSE)
    payload: ResponsePayload = F("Answer.")


class ErrorMessage(Envelope):
    """Typed error."""

    type: Literal[MessageType.ERROR] = F("Message type.", default=MessageType.ERROR)
    payload: ErrorPayload = F("Error details.")


class AckMessage(Envelope):
    """Acknowledgement of a message."""

    type: Literal[MessageType.ACK] = F("Message type.", default=MessageType.ACK)
    payload: AckPayload = F("Acknowledgement.")


class CapabilityMessage(Envelope):
    """Capability-card announcement."""

    type: Literal[MessageType.CAPABILITY] = F("Message type.", default=MessageType.CAPABILITY)
    payload: CapabilityPayload = F("Capability card.")


class VerdictMessage(Envelope):
    """Correlation / courtroom decision."""

    type: Literal[MessageType.VERDICT] = F("Message type.", default=MessageType.VERDICT)
    payload: VerdictPayload = F("Decision.")


class ReportMessage(Envelope):
    """Final unified report."""

    type: Literal[MessageType.REPORT] = F("Message type.", default=MessageType.REPORT)
    payload: ReportPayload = F("Report.")


Message = Annotated[
    ObservationMessage
    | TopologyMessage
    | ClueMessage
    | HypothesisMessage
    | SupportMessage
    | ContradictMessage
    | RequestMessage
    | ResponseMessage
    | ErrorMessage
    | AckMessage
    | CapabilityMessage
    | VerdictMessage
    | ReportMessage,
    Field(discriminator="type"),
]

MESSAGE_CLASSES: dict[MessageType, type[Envelope]] = {
    MessageType.OBSERVATION: ObservationMessage,
    MessageType.TOPOLOGY: TopologyMessage,
    MessageType.CLUE: ClueMessage,
    MessageType.HYPOTHESIS: HypothesisMessage,
    MessageType.SUPPORT: SupportMessage,
    MessageType.CONTRADICT: ContradictMessage,
    MessageType.REQUEST: RequestMessage,
    MessageType.RESPONSE: ResponseMessage,
    MessageType.ERROR: ErrorMessage,
    MessageType.ACK: AckMessage,
    MessageType.CAPABILITY: CapabilityMessage,
    MessageType.VERDICT: VerdictMessage,
    MessageType.REPORT: ReportMessage,
}

_ADAPTER: TypeAdapter[Envelope] = TypeAdapter(Message)


def parse_message(data: dict[str, Any] | str | bytes) -> Envelope:
    """Validate a wire message (dict or JSON) into its typed model."""
    if isinstance(data, str | bytes):
        return _ADAPTER.validate_json(data)
    return _ADAPTER.validate_python(data)


def dump_message(msg: Envelope) -> dict[str, Any]:
    """Serialise to a JSON-compatible dict (the wire form)."""
    return msg.model_dump(mode="json")


def to_json(msg: Envelope) -> str:
    return json.dumps(dump_message(msg), sort_keys=True, separators=(",", ":"))


def content_id(
    msg_type: MessageType,
    sender: str,
    correlation_id: str,
    causation_id: str | None,
    payload: ProtocolModel,
) -> str:
    """Deterministic msg_id: hash of everything except timestamp and recipient."""
    n = int(get_value(load_config("protocol"), "msg_id_hash_hex_chars"))
    body = json.dumps(
        [msg_type.value, sender, correlation_id, causation_id, payload.model_dump(mode="json")],
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{msg_type.value.lower()}-{hashlib.sha256(body.encode()).hexdigest()[:n]}"


def make_message(
    msg_type: MessageType,
    *,
    sender: str,
    correlation_id: str,
    payload: ProtocolModel,
    timestamp: datetime,
    recipient: str = BOARD,
    parent: Envelope | None = None,
) -> Envelope:
    """Build a message of ``msg_type``; ``parent`` sets causation_id and depth."""
    cls = MESSAGE_CLASSES[msg_type]
    causation = parent.msg_id if parent is not None else None
    return cls.model_validate(
        {
            "schema_version": get_vocabulary().version,
            "msg_id": content_id(msg_type, sender, correlation_id, causation, payload),
            "correlation_id": correlation_id,
            "causation_id": causation,
            "depth": parent.depth + 1 if parent is not None else 0,
            "sender": sender,
            "recipient": recipient,
            "timestamp": timestamp,
            "payload": payload,
        }
    )
