"""MCP server: NetCoop's diagnosis, telemetry and traces as Model Context Protocol tools.

    netcoop mcp                     # stdio transport (for MCP clients such as Claude Code)

Tools return plain JSON-able dicts. Every tool only reads local files the caller names, and
writes only under the runs directory; nothing touches network devices (simulated remediation
only, as everywhere in NetCoop). External agents join a diagnosis through ``diagnose`` by
supplying a capability card and their findings (protocol 1.0 lite or 2.0).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from netcoop.api import DEFAULT_RUNS_DIR

TRACE, REPORT_JSON, REPORT_MD, MANIFEST = "trace.jsonl", "report.json", "report.md", "manifest.json"


# ----------------------------------------------------------------------------- tool implementations
def _run_dir(incident_id: str, runs_dir: str | None) -> Path:
    d = Path(runs_dir) if runs_dir else DEFAULT_RUNS_DIR
    run = d / incident_id
    if not (run / MANIFEST).is_file():
        raise ValueError(f"no run {incident_id!r} under {d}")
    return run


def diagnose(
    path: str,
    runs_dir: str | None = None,
    external_card: dict[str, Any] | None = None,
    external_messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Diagnose a run directory or telemetry file; optionally with an external agent's findings."""
    from netcoop.agents.external import ExternalAgent
    from netcoop.agents.registry import create_agents
    from netcoop.orchestrator.orchestrator import Orchestrator

    src = Path(path)
    if not src.exists():
        raise ValueError(f"input {path!r} does not exist")
    agents = create_agents()
    if external_card is not None:
        agents.append(ExternalAgent(external_card, external_messages or []))
    res = Orchestrator(agents=agents).run(
        src, out_dir=Path(runs_dir) if runs_dir else DEFAULT_RUNS_DIR
    )
    assert res.report is not None
    return {
        "incident_id": res.report.incident_id,
        "run_dir": str(res.run_dir),
        "report": json.loads(res.report.model_dump_json()),
        "message_counts": res.board.counts(),
    }


def translate(path: str) -> dict[str, Any]:
    """Run only the Translator: dialects, stats and typed errors (data-quality check)."""
    from netcoop.translator.translator import Translator

    r = Translator().translate(Path(path), Path(path).name)
    return {
        "dialects": r.dialects,
        "stats": r.stats,
        "unknown_fields": r.unknown_fields,
        "errors": [json.loads(e.model_dump_json()) for e in r.errors],
    }


def list_runs(runs_dir: str | None = None) -> list[dict[str, Any]]:
    """Runs in the runs directory with status and root cause."""
    d = Path(runs_dir) if runs_dir else DEFAULT_RUNS_DIR
    out = []
    for run in sorted(p for p in d.iterdir() if (p / MANIFEST).is_file()) if d.is_dir() else []:
        m = json.loads((run / MANIFEST).read_text(encoding="utf-8"))
        rep = (
            json.loads((run / REPORT_JSON).read_text(encoding="utf-8"))
            if (run / REPORT_JSON).is_file()
            else {}
        )
        out.append(
            {
                "incident_id": run.name,
                "paused": bool(m.get("paused")),
                "status": rep.get("status"),
                "root_cause": rep.get("suspected_root_cause"),
                "confidence": rep.get("confidence"),
            }
        )
    return out


def get_report(incident_id: str, fmt: str = "json", runs_dir: str | None = None) -> Any:
    """The unified report of a run, as A7 JSON (fmt='json') or Markdown (fmt='md')."""
    run = _run_dir(incident_id, runs_dir)
    if fmt == "md":
        return (run / REPORT_MD).read_text(encoding="utf-8")
    return json.loads((run / REPORT_JSON).read_text(encoding="utf-8"))


def get_trace(
    incident_id: str,
    message_type: str | None = None,
    sender: str | None = None,
    limit: int = 50,
    runs_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Board messages of a run (optionally filtered by type and sender), oldest first."""
    run = _run_dir(incident_id, runs_dir)
    out = []
    for line in (run / TRACE).read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        msg = rec["msg"]
        if (message_type is None or msg["type"] == message_type.upper()) and (
            sender is None or msg["sender"] == sender
        ):
            out.append({"seq": rec["seq"], "round": rec["round"], **msg})
            if len(out) >= limit:
                break
    return out


def get_topology(incident_id: str, runs_dir: str | None = None) -> dict[str, Any]:
    """Topology the Translator built for a run (nodes, directed links, root)."""
    topo = get_trace(incident_id, "TOPOLOGY", limit=1, runs_dir=runs_dir)
    if not topo:
        return {"present": False}
    p = topo[0]["payload"]
    return {
        "present": True,
        "root": p.get("upstream_root"),
        "nodes": [
            {"id": n["entity"]["entity_id"], "type": n["entity"]["entity_type"]} for n in p["nodes"]
        ],
        "links": [
            {"id": e["link_id"], "a": e["a"], "b": e["b"], "directed": e["directed"]}
            for e in p["edges"]
        ],
    }


def review_actions(
    incident_id: str,
    approve: list[int] | None = None,
    reject: list[int] | None = None,
    reviewer: str = "mcp-client",
    note: str = "",
    runs_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Record a human decision on recommended actions (appended to the trace)."""
    from netcoop.review import Decision, review

    decisions = [Decision(i, True, note) for i in approve or []] + [
        Decision(i, False, note) for i in reject or []
    ]
    return review(_run_dir(incident_id, runs_dir), decisions, reviewer)


TOOLS = (diagnose, translate, list_runs, get_report, get_trace, get_topology, review_actions)


# ----------------------------------------------------------------------------- server
def build_server() -> Any:
    from mcp.server.mcpserver import MCPServer

    from netcoop.catalogue import CATALOGUE_DIR
    from netcoop.protocol.schema_export import SCHEMA_DIR
    from netcoop.protocol.vocabulary import VOCAB_DIR

    server = MCPServer(
        name="netcoop",
        version="0.1.0",
        instructions="NetCoop AI: multi-agent network fault diagnosis. Diagnose telemetry, read "
        "reports and traces, and join a diagnosis as an external agent.",
    )
    for fn in TOOLS:
        server.tool(name=fn.__name__, description=(fn.__doc__ or "").strip())(fn)

    @server.resource(
        "netcoop://schemas/message",
        name="message-schema",
        mime_type="application/json",
        description="JSON Schema of every netcoop protocol message.",
    )
    def message_schema() -> str:
        return (SCHEMA_DIR / "message.json").read_text(encoding="utf-8")

    @server.resource(
        "netcoop://vocabulary/metrics",
        name="metrics",
        mime_type="application/yaml",
        description="Canonical metric vocabulary (names, units, ranges).",
    )
    def metrics() -> str:
        return (VOCAB_DIR / "metrics.yaml").read_text(encoding="utf-8")

    @server.resource(
        "netcoop://catalogue/hypotheses",
        name="hypotheses",
        mime_type="application/yaml",
        description="Fault catalogue: signatures, relations, actions.",
    )
    def hypotheses() -> str:
        return (CATALOGUE_DIR / "hypotheses.yaml").read_text(encoding="utf-8")

    return server


def main() -> None:
    build_server().run("stdio")
