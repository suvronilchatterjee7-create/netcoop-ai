"""The case board: an append-only, versioned, shared message store.

Every accepted message gets a sequence number (its board version). The board enforces:

* **incident scoping:** a message must carry the board's correlation_id
* **idempotency:** a msg_id already on the board is a duplicate and is not stored again
* **causal integrity:** a causation_id must refer to a message already on the board
* **loop prevention:** depth above ``max_causation_depth`` is rejected
* **flood control:** at most ``per_agent_round_budget`` accepted posts per sender per round

Rejections never raise; they are returned to the poster and kept in ``rejections`` so the
orchestrator can report them. Subscribers (e.g. a future dashboard) receive each accepted
message as it is committed.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from netcoop.protocol.common import MessageType
from netcoop.protocol.messages import Envelope
from netcoop.protocol.payloads import AckStatus


@dataclass(frozen=True)
class Entry:
    seq: int
    round: int
    msg: Envelope


@dataclass(frozen=True)
class Rejection:
    round: int
    msg: Envelope
    reason: str


def message_metric(msg: Envelope) -> str | None:
    metric = getattr(msg.payload, "metric", None)
    return metric if isinstance(metric, str) else None


def message_entities(msg: Envelope) -> set[str]:
    """entity_ids a message is about (used for subscriptions and queries)."""
    p: Any = msg.payload
    out: set[str] = set()
    entity = getattr(p, "entity", None)
    if entity is not None:
        out.add(entity.entity_id)
    if getattr(p, "observed_from", None):
        out.add(p.observed_from)
    for he in getattr(p, "entities", ()) or ():
        out.add(he.entity.entity_id)
    return out


Subscriber = Callable[[Entry], None]


class Board:
    def __init__(self, incident_id: str, max_depth: int, per_agent_round_budget: int) -> None:
        self.incident_id = incident_id
        self.max_depth = max_depth
        self.budget = per_agent_round_budget
        self._entries: list[Entry] = []
        self._by_id: dict[str, Entry] = {}
        self._by_type: dict[MessageType, list[int]] = defaultdict(list)
        self._by_entity: dict[str, list[int]] = defaultdict(list)
        self._posts: Counter[tuple[str, int]] = Counter()
        self.rejections: list[Rejection] = []
        self.duplicates = 0
        self._subscribers: list[tuple[Subscriber, Callable[[Envelope], bool]]] = []

    # ------------------------------------------------------------------ writing
    def post(self, msg: Envelope, round_no: int, *, budgeted: bool = True) -> tuple[AckStatus, str]:
        """Append ``msg``; ``budgeted=False`` exempts ingestion (round 0) from flood control."""
        if msg.correlation_id != self.incident_id:
            return self._reject(
                msg, round_no, f"correlation_id {msg.correlation_id!r} is not this incident"
            )
        if msg.msg_id in self._by_id:
            self.duplicates += 1
            return AckStatus.DUPLICATE, "msg_id already on the board"
        if msg.causation_id is not None and msg.causation_id not in self._by_id:
            return self._reject(msg, round_no, f"unknown causation_id {msg.causation_id!r}")
        if msg.depth > self.max_depth:
            return self._reject(
                msg, round_no, f"causation depth {msg.depth} exceeds {self.max_depth} (loop?)"
            )
        if budgeted and self._posts[(msg.sender, round_no)] >= self.budget:
            return self._reject(
                msg, round_no, f"{msg.sender} exceeded {self.budget} posts in round {round_no}"
            )
        entry = Entry(len(self._entries), round_no, msg)
        self._entries.append(entry)
        self._by_id[msg.msg_id] = entry
        self._by_type[msg.type].append(entry.seq)
        for e in message_entities(msg):
            self._by_entity[e].append(entry.seq)
        self._posts[(msg.sender, round_no)] += 1
        for fn, pred in self._subscribers:
            if pred(msg):
                fn(entry)
        return AckStatus.ACCEPTED, ""

    def _reject(self, msg: Envelope, round_no: int, reason: str) -> tuple[AckStatus, str]:
        self.rejections.append(Rejection(round_no, msg, reason))
        return AckStatus.REJECTED, reason

    def subscribe(
        self,
        fn: Subscriber,
        types: Iterable[MessageType] | None = None,
        metric: str | None = None,
        entity: str | None = None,
    ) -> None:
        """Call ``fn(entry)`` for each future accepted message matching the filters."""
        wanted = set(types) if types else None

        def pred(m: Envelope) -> bool:
            return (
                (wanted is None or m.type in wanted)
                and (metric is None or message_metric(m) == metric)
                and (entity is None or entity in message_entities(m))
            )

        self._subscribers.append((fn, pred))

    # ------------------------------------------------------------------ reading
    @property
    def version(self) -> int:
        return len(self._entries)

    def entries(self, since: int = 0) -> list[Entry]:
        return self._entries[since:]

    def messages(self) -> list[Envelope]:
        return [e.msg for e in self._entries]

    def get(self, msg_id: str) -> Envelope | None:
        e = self._by_id.get(msg_id)
        return e.msg if e else None

    def entry(self, msg_id: str) -> Entry | None:
        return self._by_id.get(msg_id)

    def query(
        self,
        type: MessageType | None = None,
        metric: str | None = None,
        entity: str | None = None,
        sender: str | None = None,
    ) -> list[Envelope]:
        if type is not None:
            seqs = self._by_type.get(type, [])
        elif entity is not None:
            seqs = self._by_entity.get(entity, [])
        else:
            seqs = range(len(self._entries))  # type: ignore[assignment]
        out = []
        for s in seqs:
            m = self._entries[s].msg
            if entity is not None and entity not in message_entities(m):
                continue
            if metric is not None and message_metric(m) != metric:
                continue
            if sender is not None and m.sender != sender:
                continue
            out.append(m)
        return out

    def ancestors(self, msg_id: str) -> list[Envelope]:
        """Causal chain from the root to ``msg_id`` (inclusive)."""
        chain: list[Envelope] = []
        cur = self.get(msg_id)
        while cur is not None:
            chain.append(cur)
            cur = self.get(cur.causation_id) if cur.causation_id else None
        return chain[::-1]

    def counts(self) -> dict[str, int]:
        return {t.value: len(v) for t, v in sorted(self._by_type.items()) if v}
