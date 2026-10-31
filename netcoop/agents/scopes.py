"""Topology graph and signature scopes (where evidence for a hypothesis is looked for).

Scopes are named in the catalogue (config/catalogue/hypotheses.yaml). Each resolves, for a
candidate root entity, to a set of entities and/or vantage points; ``invert`` answers the
opposite question (which roots could a piece of evidence point to). Without a topology only
the root-local scopes resolve; relational ones come back empty, so agents degrade to
non-relational reasoning rather than guessing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from netcoop.protocol.payloads import TopologyEdge, TopologyPayload


@dataclass(frozen=True)
class Region:
    """Entities (matched by entity_id, no vantage) and vantages (matched by observed_from)."""

    entities: frozenset[str] = frozenset()
    vantages: frozenset[str] = frozenset()
    probes_of: frozenset[str] = frozenset()  # service entity_ids: any probe of them matches

    def matches(self, entity_id: str, observed_from: str | None) -> bool:
        if observed_from is None:
            return entity_id in self.entities
        return observed_from in self.vantages or entity_id in self.probes_of

    def ids(self) -> list[str]:
        return sorted(self.entities | self.vantages | self.probes_of)


@dataclass
class Topo:
    payload: TopologyPayload | None
    links: dict[str, TopologyEdge] = field(default_factory=dict)
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    node_types: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.payload is None:
            return
        for n in self.payload.nodes:
            self.graph.add_node(n.entity.entity_id)
            self.node_types[n.entity.entity_id] = n.entity.entity_type
        for e in self.payload.edges:
            self.links[e.link_id] = e
            if e.directed:
                self.graph.add_edge(e.a, e.b, link=e.link_id)

    @property
    def present(self) -> bool:
        return self.payload is not None

    # -- structure -------------------------------------------------------------------
    def attached_links(self, node: str) -> set[str]:
        return {lid for lid, e in self.links.items() if node in (e.a, e.b)}

    def subtree(self, node: str) -> set[str]:
        if node not in self.graph:
            return {node}
        return {node, *nx.descendants(self.graph, node)}

    def links_within(self, nodes: set[str]) -> set[str]:
        return {lid for lid, e in self.links.items() if e.a in nodes and e.b in nodes}

    def path_links_to_root(self, node: str) -> set[str]:
        out: set[str] = set()
        cur = node
        seen = {cur}
        while cur in self.graph:
            preds = list(self.graph.predecessors(cur))
            if not preds:
                break
            parent = preds[0]
            out.add(self.graph.edges[parent, cur]["link"])
            if parent in seen:
                break
            seen.add(parent)
            cur = parent
        return out

    def location(self, entity_id: str, observed_from: str | None) -> str | None:
        """Node of the network a piece of evidence is located at (link -> downstream end)."""
        if observed_from is not None:
            return observed_from
        if entity_id in self.links:
            e = self.links[entity_id]
            return e.b if e.directed else e.a
        return entity_id if entity_id in self.graph else None

    def lowest_common_upstream(self, nodes: set[str]) -> str | None:
        nodes = {n for n in nodes if n in self.graph}
        if not nodes:
            return None
        common: set[str] | None = None
        for n in nodes:
            anc = {n, *nx.ancestors(self.graph, n)}
            common = anc if common is None else common & anc
        if not common:
            return None
        # the deepest common ancestor: the one with the most ancestors of its own
        return max(sorted(common), key=lambda c: len(nx.ancestors(self.graph, c)))

    # -- scopes ----------------------------------------------------------------------
    def resolve(self, scope: str, root: str, probes: dict[str, set[str]]) -> Region:
        link = self.links.get(root)
        if scope == "root":
            return Region(entities=frozenset({root}))
        if scope == "probes_of_root":
            return Region(probes_of=frozenset({root}))
        if scope == "probes_from_root":
            return Region(vantages=frozenset({root}))
        if scope == "root_upstream":
            return Region(entities=frozenset({link.a})) if link else Region()
        if scope == "root_downstream":
            return Region(entities=frozenset({link.b})) if link else Region()
        if scope == "root_endpoints":
            return Region(entities=frozenset({link.a, link.b})) if link else Region()
        if scope == "attached_links":
            return Region(entities=frozenset(self.attached_links(root)))
        if scope == "probes_downstream":
            below = (
                self.subtree(link.b)
                if link
                else self.subtree(root)
                if root in self.graph
                else set()
            )
            return Region(vantages=frozenset(below))
        if scope == "probe_paths":
            paths: set[str] = set()
            for v in probes.get(root, set()):
                paths |= self.path_links_to_root(v)
            return Region(entities=frozenset(paths))
        raise ValueError(f"unknown scope {scope!r}")

    def invert(self, scope: str, entity_id: str, observed_from: str | None) -> set[str]:
        """Candidate roots for which evidence at (entity_id, observed_from) falls in ``scope``."""
        if scope == "root":
            return {entity_id} if observed_from is None else set()
        if scope == "probes_of_root":
            return {entity_id} if observed_from is not None else set()
        if scope == "probes_from_root":
            return {observed_from} if observed_from is not None else set()
        if observed_from is not None:
            return set()
        if scope == "root_upstream":
            return {lid for lid, e in self.links.items() if e.a == entity_id}
        if scope == "root_downstream":
            return {lid for lid, e in self.links.items() if e.b == entity_id}
        if scope == "root_endpoints":
            return {lid for lid, e in self.links.items() if entity_id in (e.a, e.b)}
        if scope == "attached_links":
            e = self.links.get(entity_id)
            return {e.a, e.b} if e else set()
        return set()

    def blast_radius(self, root: str, category: str) -> Region:
        """Locations a fault at ``root`` can plausibly affect."""
        if category == "service":
            return Region(entities=frozenset({root}), probes_of=frozenset({root}))
        link = self.links.get(root)
        if link is not None:
            below = self.subtree(link.b)
            nodes = below | {link.a}
            return Region(
                entities=frozenset(nodes | self.links_within(below) | {root}),
                vantages=frozenset(below),
            )
        below = self.subtree(root)
        return Region(
            entities=frozenset(below | self.links_within(below) | self.attached_links(root)),
            vantages=frozenset(below),
        )
