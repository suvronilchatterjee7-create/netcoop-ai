"""Topology ingestion: node lists, edge lists or edge tables -> one canonical graph.

Recognised purely through the declarative `topology` section of the mapping file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from netcoop.protocol.common import EntityRef, ErrorCode, Severity, SourceRef
from netcoop.protocol.payloads import TopologyEdge, TopologyNode, TopologyPayload
from netcoop.translator.issues import IssueLog
from netcoop.translator.mapping import Mapping, normalise_key
from netcoop.translator.quality import combine
from netcoop.translator.readers import RawTable, Record

UNKNOWN_DEVICE_TYPE = "device"


@dataclass
class Graph:
    node_types: dict[str, str | None] = field(default_factory=dict)
    parents: dict[str, str] = field(default_factory=dict)
    edges: dict[str, TopologyEdge] = field(default_factory=dict)
    by_pair: dict[frozenset[str], str] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)

    @property
    def present(self) -> bool:
        return bool(self.node_types)

    def entity_type(self, node_id: str) -> str | None:
        """Vocabulary entity type of a node; None if the node is unknown."""
        if node_id not in self.node_types:
            return None
        return self.node_types[node_id] or UNKNOWN_DEVICE_TYPE

    def link_between(self, a: str, b: str) -> str | None:
        return self.by_pair.get(frozenset((a, b)))

    def root(self) -> str | None:
        children = {e.b for e in self.edges.values() if e.directed}
        parents = {e.a for e in self.edges.values() if e.directed}
        roots = sorted(parents - children)
        return roots[0] if len(roots) == 1 else None


def _first(rec: dict[str, object], keys: list[str]) -> object | None:
    for k in keys:
        if k in rec and rec[k] not in (None, ""):
            return rec[k]
    return None


def _norm_rec(rec: Record) -> dict[str, object]:
    return {normalise_key(k): v for k, v in rec.items()}


def is_topology_table(table: RawTable, mapping: Mapping) -> bool:
    topo = mapping.topology
    if table.section is not None:
        key = normalise_key(table.section)
        return key in map(normalise_key, topo["node_list_keys"] + topo["edge_list_keys"])
    keys = {normalise_key(k) for _, r in table.records[:50] for k in r}
    if keys & mapping.timestamp_fields:
        return False
    # A telemetry table that merely lost its timestamp still carries metric fields; an edge
    # table carries at most a capacity. Only the latter is topology.
    capacity = {normalise_key(k) for k in topo["capacity_fields"]}
    if any(k in mapping.metric_aliases for k in keys - capacity):
        return False
    return any(
        {normalise_key(a), normalise_key(b)} <= keys for a, b in topo["edge_endpoint_fields"]
    )


def build_graph(tables: list[RawTable], mapping: Mapping, log: IssueLog) -> Graph:
    t = mapping.topology
    nkeys = [normalise_key(k) for k in t["node_list_keys"]]
    id_f = [normalise_key(k) for k in t["node_id_fields"]]
    type_f = [normalise_key(k) for k in t["node_type_fields"]]
    parent_f = [normalise_key(k) for k in t["node_parent_fields"]]
    edge_id_f = [normalise_key(k) for k in t["edge_id_fields"]]
    pairs = [(normalise_key(a), normalise_key(b)) for a, b in t["edge_endpoint_fields"]]
    directed_pairs = {(normalise_key(a), normalise_key(b)) for a, b in t["directed_pairs"]}
    row_type_f = [normalise_key(k) for k in t["edge_row_type_fields"]]
    type_values = {normalise_key(k): v for k, v in t["node_type_values"].items()}
    cap_f = {normalise_key(k): u for k, u in t["capacity_fields"].items()}
    g = Graph()

    def node_type(raw: object, source: str) -> str | None:
        if raw is None:
            return None
        mapped = type_values.get(normalise_key(str(raw)))
        if mapped is None:
            log.add(
                ErrorCode.TYPE_MISMATCH,
                Severity.WARNING,
                source,
                f"unknown node type {raw!r}; treated as generic device",
                field="node_type",
            )
        return mapped

    def add_node(nid: str, ntype: str | None) -> None:
        if ntype is not None or nid not in g.node_types:
            g.node_types[nid] = ntype if ntype is not None else g.node_types.get(nid)

    raw_edges: list[tuple[str, str, str, bool | None, str | None, float | None]] = []
    for table in tables:
        g.sources.append(table.source)
        is_node_list = table.section is not None and normalise_key(table.section) in nkeys
        for loc, rec in table.records:
            r = _norm_rec(rec)
            if is_node_list:
                nid = _first(r, id_f)
                if nid is None:
                    log.add(
                        ErrorCode.MISSING_FIELD,
                        Severity.RECOVERABLE,
                        table.source,
                        "topology node without id skipped",
                        locator=loc,
                    )
                    continue
                add_node(str(nid), node_type(_first(r, type_f), table.source))
                parent = _first(r, parent_f)
                if parent is not None:
                    g.parents[str(nid)] = str(parent)
                continue
            pair = next(
                (
                    (a, b)
                    for a, b in pairs
                    if r.get(a) not in (None, "") and r.get(b) not in (None, "")
                ),
                None,
            )
            if pair is None:
                log.add(
                    ErrorCode.MISSING_FIELD,
                    Severity.RECOVERABLE,
                    table.source,
                    "topology edge without two endpoints skipped",
                    locator=loc,
                )
                continue
            a, b = str(r[pair[0]]), str(r[pair[1]])
            add_node(a, None)
            add_node(b, node_type(_first(r, row_type_f), table.source))
            cap = None
            for k, unit in cap_f.items():
                if r.get(k) not in (None, ""):
                    info = mapping.unit(unit) or mapping.unit_from_suffix(k, "data_rate")
                    try:
                        cap = float(r[k]) * (info.factor if info else 1.0)  # type: ignore[arg-type]
                    except (TypeError, ValueError):
                        log.add(
                            ErrorCode.TYPE_MISMATCH,
                            Severity.WARNING,
                            table.source,
                            "non-numeric link capacity ignored",
                            field=k,
                            locator=loc,
                        )
                    break
            eid = _first(r, edge_id_f)
            raw_edges.append(
                (
                    str(eid) if eid else "",
                    a,
                    b,
                    True if pair in directed_pairs else None,
                    table.source,
                    cap,
                )
            )

    # Edges implied by node parents when no explicit edge lists exist for them.
    explicit = {frozenset((a, b)) for _, a, b, *_ in raw_edges}
    for child, parent in sorted(g.parents.items()):
        if frozenset((parent, child)) not in explicit:
            raw_edges.append(("", parent, child, True, None, None))
        add_node(parent, None)

    template = str(t["link_id_template"])
    for eid, a, b, directed, _src, cap in raw_edges:
        if directed is None:
            if g.parents.get(b) == a:
                directed = True
            elif g.parents.get(a) == b:
                a, b, directed = b, a, True
            else:
                directed = False
        link_id = eid or template.format(a=a, b=b)
        edge = TopologyEdge(link_id=link_id, a=a, b=b, directed=directed, capacity=cap)
        g.edges[link_id] = edge
        g.by_pair[frozenset((a, b))] = link_id
    return g


def topology_payload(g: Graph, dialects: dict[str, str]) -> TopologyPayload:
    nodes = tuple(
        TopologyNode(
            entity=EntityRef(entity_id=nid, entity_type=g.entity_type(nid) or UNKNOWN_DEVICE_TYPE)
        )
        for nid in sorted(g.node_types)
    )
    typed = sum(1 for v in g.node_types.values() if v is not None)
    completeness = typed / len(g.node_types) if g.node_types else 0.0
    issues = ("node_type_unknown",) if typed < len(g.node_types) else ()
    root = g.root()
    return TopologyPayload(
        nodes=nodes,
        edges=tuple(g.edges[k] for k in sorted(g.edges)),
        upstream_root=root,
        sources=tuple(
            SourceRef(source=s, dialect=dialects.get(s, "unrecognised"), locator="file")
            for s in dict.fromkeys(g.sources)
        ),
        quality=combine(completeness, 1.0, 1.0, 1.0, issues),
    )
