"""Signature assessment shared by specialists (own clues) and the correlator (all clues).

An element of a catalogue signature is *satisfied*, *violated* or *unknown* for a candidate
root, judged from the clues found in the element's scope. Passing ``used_observations``
makes the assessment independence-aware: clues whose source observations were already
counted for another element are ignored, so one measurement cannot support two elements.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from netcoop.agents.scopes import Topo
from netcoop.catalogue import Element
from netcoop.protocol.common import Direction, Statistic
from netcoop.protocol.messages import Envelope
from netcoop.protocol.payloads import CluePayload

DIRECTION = {
    "above": Direction.ABOVE,
    "below": Direction.BELOW,
    "changed": Direction.CHANGED,
    "rising": Direction.ABOVE,
}
SATISFIED, VIOLATED, UNKNOWN = "satisfied", "violated", "unknown"


@dataclass(frozen=True)
class Assessment:
    status: str
    good: tuple[Envelope, ...]
    bad: tuple[Envelope, ...]

    @property
    def clues(self) -> tuple[Envelope, ...]:
        return self.good if self.status == SATISFIED else self.bad


def assess(
    e: Element,
    root: str,
    clues_by_metric: Mapping[str, Sequence[Envelope]],
    topo: Topo,
    probes: Mapping[str, set[str]],
    used_observations: set[str] | None = None,
) -> Assessment:
    region = topo.resolve(e.scope, root, dict(probes))
    want_slope = e.direction == "rising"
    matching = []
    for c in clues_by_metric.get(e.metric, ()):
        p: CluePayload = c.payload
        if (p.statistic is Statistic.SLOPE) != want_slope:
            continue
        if not region.matches(p.entity.entity_id, p.observed_from):
            continue
        if used_observations is not None and used_observations & set(p.source_observation_ids):
            continue
        matching.append(c)
    if not matching:
        return Assessment(UNKNOWN, (), ())

    def deviates(c: Envelope) -> bool:
        p: CluePayload = c.payload
        return p.significant and p.direction is DIRECTION[e.direction]

    good = [c for c in matching if deviates(c) == (e.expect == "deviates")]
    bad = [c for c in matching if c not in good]
    if e.quorum is not None:
        ok = len(good) / len(matching) >= e.quorum
    else:
        ok = bool(good) if e.expect == "deviates" else not bad
    return Assessment(SATISFIED if ok else VIOLATED, tuple(good), tuple(bad))
