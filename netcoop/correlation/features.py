"""Turn a finished board into scored-ready candidates (docs/SCORING.md section 4).

* **Candidates** are the distinct (hypothesis type, root) pairs proposed by any agent;
  duplicates from several proposers merge into one candidate.
* **Signature status** of every catalogue element is recomputed from *all* agents' clues,
  so the correlator never relies on a proposer's own view. Elements are assessed required
  first; a source observation counted for one element is not counted again for another
  (independence: one measurement, one vote).
* **Analytic stances** are SUPPORT/CONTRADICT messages justified by clues the stance sender
  did *not* author (e.g. topology localisation). They carry information the signature does
  not, and become a separate feature. Stances justified by the sender's own clues are already
  counted through the signature and are ignored, to avoid double counting.
* **Context** records what the data allows: observed metrics, significant-clue count, mean
  quality, and which fault types could not be assessed at all.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import fmean
from typing import Any

from netcoop.agents.scopes import Topo
from netcoop.agents.signature import SATISFIED, UNKNOWN, VIOLATED, assess
from netcoop.board.board import Board
from netcoop.catalogue import Catalogue, HypothesisSpec, get_catalogue
from netcoop.protocol.common import EntityRole, MessageType
from netcoop.protocol.messages import Envelope
from netcoop.protocol.payloads import (
    CluePayload,
    HypothesisEntity,
    HypothesisPayload,
    ObservationPayload,
    StancePayload,
    TopologyPayload,
)
from netcoop.protocol.vocabulary import get_vocabulary

T = MessageType
SUPPORT, CONTRADICT, NONE = "support", "contradict", "none"


@dataclass
class Candidate:
    hypothesis_type: str
    root: str
    root_type: str
    hypothesis_msg_ids: list[str]
    proposers: list[str]
    entities: tuple[HypothesisEntity, ...]
    statuses: tuple[str, ...] = ()
    element_clues: tuple[tuple[str, ...], ...] = ()
    analytic: str = NONE
    analytic_ids: tuple[str, ...] = ()
    quality: float = 0.0

    @property
    def key(self) -> str:
        return f"{self.hypothesis_type}@{self.root}"

    def to_record(self) -> dict[str, Any]:
        return {
            "type": self.hypothesis_type,
            "root": self.root,
            "statuses": list(self.statuses),
            "analytic": self.analytic,
            "quality": self.quality,
        }


@dataclass
class Context:
    observed_metrics: set[str] = field(default_factory=set)
    assessed_metrics: set[str] = field(default_factory=set)  # metrics some agent posted clues on
    n_significant: int = 0
    mean_quality: float = 0.0
    unassessable: list[str] = field(default_factory=list)  # fault types present but not assessable
    not_applicable: list[str] = field(default_factory=list)  # fault types with no possible root


def _order(h: HypothesisSpec) -> list[int]:
    """Assessment order: required elements first (they claim shared observations first)."""
    return sorted(range(len(h.signature)), key=lambda i: (h.signature[i].role != "required", i))


def evaluate_candidate(
    c: Candidate,
    h: HypothesisSpec,
    clues: dict[str, list[Envelope]],
    topo: Topo,
    probes: dict[str, set[str]],
) -> None:
    used: set[str] = set()
    statuses = [UNKNOWN] * len(h.signature)
    ids: list[tuple[str, ...]] = [()] * len(h.signature)
    qualities: list[float] = []
    for i in _order(h):
        a = assess(h.signature[i], c.root, clues, topo, probes, used_observations=used)
        statuses[i] = a.status
        if a.status != UNKNOWN:
            ids[i] = tuple(m.msg_id for m in a.clues)
            for m in (*a.good, *a.bad):
                used |= set(m.payload.source_observation_ids)
                qualities.append(m.payload.data_quality)
    c.statuses, c.element_clues = tuple(statuses), tuple(ids)
    c.quality = fmean(qualities) if qualities else 0.0


def extract(board: Board, catalogue: Catalogue | None = None) -> tuple[list[Candidate], Context]:
    cat = catalogue or get_catalogue()
    vocab = get_vocabulary()
    topo_msgs = board.query(type=T.TOPOLOGY)
    topo = Topo(
        topo_msgs[-1].payload
        if topo_msgs and isinstance(topo_msgs[-1].payload, TopologyPayload)
        else None
    )

    ctx = Context()
    probes: dict[str, set[str]] = defaultdict(set)
    entity_types: dict[str, str] = {}
    qualities = []
    for m in board.query(type=T.OBSERVATION):
        o: ObservationPayload = m.payload
        ctx.observed_metrics.add(o.metric)
        entity_types[o.entity.entity_id] = o.entity.entity_type
        qualities.append(o.quality.score)
        if o.observed_from is not None:
            probes[o.entity.entity_id].add(o.observed_from)
    if topo.payload is not None:
        for n in topo.payload.nodes:
            entity_types.setdefault(n.entity.entity_id, n.entity.entity_type)
        for lid in topo.links:
            entity_types.setdefault(lid, "link")
    ctx.mean_quality = fmean(qualities) if qualities else 0.0

    clues: dict[str, list[Envelope]] = defaultdict(list)
    author: dict[str, str] = {}
    for m in board.query(type=T.CLUE):
        p: CluePayload = m.payload
        clues[p.metric].append(m)
        ctx.assessed_metrics.add(p.metric)
        author[m.msg_id] = m.sender
        ctx.n_significant += int(p.significant)

    for hid, h in cat.hypotheses.items():
        roots = [e for e, t in entity_types.items() if h.locus.admits(e, t)]
        if not roots:
            ctx.not_applicable.append(hid)
            continue
        groups: dict[str, set[str]] = defaultdict(set)
        for e in h.required:
            groups[e.group_key].add(e.metric)
        # assessable = some agent actually evaluated a required metric (observed is not enough:
        # data nobody analysed cannot rule a fault out)
        if not all(ms & ctx.assessed_metrics for ms in groups.values()):
            ctx.unassessable.append(hid)

    by_key: dict[tuple[str, str], Candidate] = {}
    for m in board.query(type=T.HYPOTHESIS):
        hp: HypothesisPayload = m.payload
        root = next((he.entity for he in hp.entities if he.role is EntityRole.ROOT), None)
        if root is None or hp.hypothesis_type not in cat.hypotheses:
            continue
        key = (hp.hypothesis_type, root.entity_id)
        if key not in by_key:
            by_key[key] = Candidate(
                hp.hypothesis_type, root.entity_id, root.entity_type, [], [], hp.entities
            )
        by_key[key].hypothesis_msg_ids.append(m.msg_id)
        by_key[key].proposers.append(m.sender)

    stances: dict[str, list[Envelope]] = defaultdict(list)
    for t in (T.SUPPORT, T.CONTRADICT):
        for m in board.query(type=t):
            s: StancePayload = m.payload
            if all(author.get(cid) == m.sender for cid in s.clue_ids):
                continue  # justified by the sender's own clues: already in the signature
            stances[s.target_msg_id].append(m)

    out = []
    for (hid, _), c in sorted(by_key.items()):
        evaluate_candidate(c, cat.hypotheses[hid], clues, topo, probes)
        analytic = [m for mid in c.hypothesis_msg_ids for m in stances.get(mid, [])]
        if analytic:
            best = max(analytic, key=lambda m: (m.payload.strength, m.type is T.CONTRADICT))
            c.analytic = SUPPORT if best.type is T.SUPPORT else CONTRADICT
            c.analytic_ids = tuple(m.msg_id for m in analytic)
        out.append(c)
    del vocab
    return out, ctx


def explains(cause: Candidate, effect: Candidate, cat: Catalogue, topo: Topo) -> bool:
    """Catalogue causal precedence: ``cause`` explains ``effect`` located in its blast radius."""
    if effect.hypothesis_type not in cat.hypotheses[cause.hypothesis_type].explains:
        return False
    category = get_vocabulary().category_of(cause.root_type)
    region = topo.blast_radius(cause.root, category)
    return region.matches(effect.root, None) or effect.root in region.vantages


__all__ = [
    "CONTRADICT",
    "NONE",
    "SATISFIED",
    "SUPPORT",
    "VIOLATED",
    "Candidate",
    "Context",
    "explains",
    "extract",
]
