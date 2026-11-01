"""Standard-library HTTP server behind the dashboard (``netcoop serve``, docs/WEB.md).

Endpoints (all JSON unless noted):

- ``GET /``                         the dashboard page (static files in ``netcoop/web/static``)
- ``GET /api/config``               values the page needs (replay pace)
- ``GET /api/inputs``               run folders that can be diagnosed, by collection
- ``GET /api/diagnose?input=<id>``  Server-Sent Events: one ``message`` event per board
                                    message as it is committed, then ``done`` or ``failed``
- ``GET /api/runs``                 past dashboard runs
- ``GET /api/runs/<incident>``      report, manifest and the decision chain of one run
- ``GET /api/evaluation``           headline metrics from docs/EVALUATION.md

The server binds to loopback, and inputs are resolved only inside the configured roots.
"""

from __future__ import annotations

import json
import mimetypes
import queue
import re
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from netcoop.config import get_value, load_config
from netcoop.demo import evaluation_headline

mimetypes.add_type("font/woff2", ".woff2")  # not in every platform's registry (e.g. Windows)

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).resolve().parent / "static"
INCIDENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
# Messages listed individually in the decision chain; the rest are counted.
COUNTED = {"OBSERVATION", "CLUE", "CAPABILITY"}


def _cfg(key: str) -> Any:
    return get_value(load_config("web"), key)


def _runs_dir() -> Path:
    return REPO_ROOT / str(_cfg("runs.dir"))


# --------------------------------------------------------------------------- inputs


def _meta(run: Path) -> dict[str, Any]:
    try:
        gt = json.loads((run / "meta.json").read_text(encoding="utf-8")).get("ground_truth", {})
    except (OSError, ValueError):
        gt = {}
    return {
        "truth": gt.get("root_cause") or gt.get("scenario"),
        "intensity": gt.get("intensity"),
        "noise": gt.get("noise"),
        "missing_rate": gt.get("missing_rate"),
        "dialect": gt.get("dialect"),
    }


def _run_dirs(root: Path) -> list[Path]:
    """Run folders under a root: direct children with meta.json, or one level deeper."""
    if not root.is_dir():
        return []
    found: list[Path] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        if (d / "meta.json").is_file():
            found.append(d)
        else:
            found.extend(sorted(c for c in d.iterdir() if (c / "meta.json").is_file()))
    return found


def list_inputs() -> list[dict[str, Any]]:
    limit = int(_cfg("inputs.max_listed"))
    out = []
    for rel in _cfg("inputs.roots"):
        runs = _run_dirs(REPO_ROOT / rel)
        if not runs:
            continue
        shown = runs if rel.endswith("samples") else runs[:limit]
        out.append(
            {
                "collection": rel,
                "total": len(runs),
                "runs": [
                    {
                        "id": f"{rel}/{r.relative_to(REPO_ROOT / rel).as_posix()}",
                        "name": r.name,
                        **_meta(r),
                    }
                    for r in shown
                ],
            }
        )
    return out


def resolve_input(input_id: str) -> Path | None:
    """Map an input id to a run folder inside one of the configured roots, or None."""
    for rel in _cfg("inputs.roots"):
        root = (REPO_ROOT / rel).resolve()
        if not input_id.startswith(rel + "/"):
            continue
        cand = (REPO_ROOT / input_id).resolve()
        if cand.is_relative_to(root) and cand != root and (cand / "meta.json").is_file():
            return cand
        # A bare run name typed into the filter: search the collection for it.
        name = input_id[len(rel) + 1 :]
        for r in _run_dirs(root):
            if r.name == name:
                return r
    return None


# --------------------------------------------------------------------------- messages


def _ent(e: Any) -> str:
    return str(getattr(e, "entity_id", e))


def _root_entity(entities: Any) -> str:
    ents = list(entities or ())
    for he in ents:
        if str(getattr(he, "role", "")).endswith("root"):
            return _ent(he.entity)
    return _ent(ents[0].entity) if ents else "-"


def summarize(msg: Any) -> str:
    """One readable line for a board message."""
    t = msg.type.value
    p = msg.payload
    try:
        if t == "OBSERVATION":
            return f"{p.metric} on {_ent(p.entity)} ({len(p.points)} samples)"
        if t == "TOPOLOGY":
            return f"{len(p.nodes)} devices and services, {len(p.edges)} links"
        if t == "CAPABILITY":
            return str(p.card.description)
        if t == "CLUE":
            mark = "abnormal" if p.significant else "normal"
            return (
                f"{p.metric} on {_ent(p.entity)}: {mark} "
                f"({p.deviation:.2g} {p.deviation_unit}, {p.direction.value})"
            )
        if t == "HYPOTHESIS":
            return (
                f"{p.hypothesis_type} at {_root_entity(p.entities)} "
                f"(proposer confidence {p.local_confidence:.2f})"
            )
        if t == "REQUEST":
            return f"asks for {p.capability}: {p.reason}"
        if t == "RESPONSE":
            return f"{p.status.value}" + (f": {p.detail}" if p.detail else "")
        if t in ("SUPPORT", "CONTRADICT"):
            return str(p.note or p.reason_code)
        if t == "VERDICT":
            what = (
                f" {p.hypothesis_type} at {_root_entity(p.entities)}" if p.hypothesis_type else ""
            )
            return f"{p.decision.value}{what}, confidence {p.confidence:.2f} ({p.method})"
        if t == "REPORT":
            return f"{p.report.status.value}: {p.report.suspected_root_cause}"
        if t == "ERROR":
            return f"{p.code.value} ({p.severity.value}): {p.message}"
        if t == "ACK":
            return str(p.status.value) + (f": {p.reason}" if p.reason else "")
    except AttributeError:
        pass
    return str(t).lower()


def message_event(seq: int, rnd: int, msg: Any) -> dict[str, Any]:
    return {
        "seq": seq,
        "round": rnd,
        "type": msg.type.value,
        "sender": msg.sender,
        "recipient": msg.recipient,
        "msg_id": msg.msg_id,
        "causation_id": msg.causation_id,
        "summary": summarize(msg),
    }


# --------------------------------------------------------------------------- runs


def _trace_events(run_dir: Path) -> list[dict[str, Any]]:
    from netcoop.protocol.messages import parse_message

    events = []
    with (run_dir / "trace.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            events.append(message_event(row["seq"], row["round"], parse_message(row["msg"])))
    return events


def run_detail(incident: str) -> dict[str, Any] | None:
    if not INCIDENT_RE.match(incident):
        return None
    run_dir = _runs_dir() / incident
    if not (run_dir / "report.json").is_file():
        return None
    events = _trace_events(run_dir)
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    counts: dict[str, dict[str, int]] = {}
    for e in events:
        if e["type"] in COUNTED:
            counts.setdefault(e["type"], {}).setdefault(e["sender"], 0)
            counts[e["type"]][e["sender"]] += 1
    # Clues and observations the report's evidence is traced to (x_netcoop.evidence_provenance).
    wanted: set[str] = set()
    for prov in (report.get("x_netcoop") or {}).get("evidence_provenance", []):
        wanted.add(prov["clue_id"])
        wanted.update(prov.get("observation_ids", []))
    return {
        "incident": incident,
        "report": report,
        "manifest": json.loads((run_dir / "manifest.json").read_text(encoding="utf-8")),
        "counts": counts,
        "chain": [e for e in events if e["type"] not in COUNTED],
        "cited": {e["msg_id"]: e for e in events if e["msg_id"] in wanted},
        "files": {
            "report_md": _rel(run_dir / "report.md"),
            "trace": _rel(run_dir / "trace.jsonl"),
        },
    }


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:  # runs.dir may point outside the repository
        return str(path)


def list_runs() -> list[dict[str, Any]]:
    root = _runs_dir()
    if not root.is_dir():
        return []
    out = []
    for d in root.iterdir():
        try:
            report = json.loads((d / "report.json").read_text(encoding="utf-8"))
            manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        inputs = [Path(str(p)) for p in manifest.get("inputs") or []]
        # The manifest lists input files; name the run folder that holds them.
        folder = (inputs[0].parent if inputs[0].suffix else inputs[0]).name if inputs else None
        out.append(
            {
                "incident": d.name,
                "status": report.get("status"),
                "root_cause": report.get("suspected_root_cause"),
                "confidence": report.get("confidence"),
                "input": folder,
                "mtime": (d / "report.json").stat().st_mtime,
            }
        )
    return sorted(out, key=lambda r: -float(r["mtime"]))


# --------------------------------------------------------------------------- handler


class Handler(BaseHTTPRequestHandler):
    server_version = "netcoop"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        pass

    def _json(self, body: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _static(self, name: str) -> None:
        path = (STATIC / name).resolve()
        if not path.is_relative_to(STATIC) or not path.is_file():
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - stdlib name
        url = urlparse(self.path)
        path = url.path
        if path in ("/", "/index.html"):
            self._static("index.html")
        elif path.startswith("/static/"):
            self._static(path[len("/static/") :])
        elif path == "/api/config":
            self._json({"replay_step_ms": int(_cfg("replay.step_ms"))})
        elif path == "/api/inputs":
            self._json(list_inputs())
        elif path == "/api/runs":
            self._json(list_runs())
        elif path.startswith("/api/runs/"):
            detail = run_detail(path[len("/api/runs/") :])
            if detail is None:
                self._json({"error": "unknown run"}, HTTPStatus.NOT_FOUND)
            else:
                self._json(detail)
        elif path == "/api/evaluation":
            self._json(evaluation_headline())
        elif path == "/api/diagnose":
            self._diagnose(parse_qs(url.query).get("input", [""])[0])
        else:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def _send_event(self, event: str, data: Any) -> None:
        self.wfile.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode())
        self.wfile.flush()

    def _diagnose(self, input_id: str) -> None:
        run = resolve_input(input_id)
        if run is None:
            self._json({"error": f"unknown input {input_id!r}"}, HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        events: queue.Queue[tuple[str, Any]] = queue.Queue()

        def work() -> None:
            from netcoop.api import run_diagnosis
            from netcoop.orchestrator.orchestrator import Event

            def hook(e: object) -> None:
                if isinstance(e, Event) and e.kind == "message":
                    events.put(("message", message_event(e.data["seq"], e.round, e.data["msg"])))

            try:
                result = run_diagnosis(run, out_dir=_runs_dir(), on_event=hook)
                incident = result.run_dir.name if result.run_dir else None
                events.put(("done", {"incident": incident}))
            except Exception as exc:  # reported to the page; the server keeps running
                events.put(("failed", {"error": f"{type(exc).__name__}: {exc}"}))

        threading.Thread(target=work, daemon=True).start()
        try:
            self._send_event("start", {"input": input_id, "name": run.name, **_meta(run)})
            while True:
                kind, data = events.get()
                self._send_event(kind, data)
                if kind in ("done", "failed"):
                    break
        except (BrokenPipeError, ConnectionResetError):
            pass  # the page navigated away; the run still finishes and is listed


def make_server(host: str | None = None, port: int | None = None) -> ThreadingHTTPServer:
    host = host or str(_cfg("server.host"))
    port = int(_cfg("server.port")) if port is None else port
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


__all__ = ["list_inputs", "list_runs", "make_server", "resolve_input", "run_detail", "summarize"]
