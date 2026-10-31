"""Phase 9 tests: pause/resume, human review, extensions and plugins, MCP server, external agent."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from netcoop.extensions import merge_section
from netcoop.generation import load_adapter
from netcoop.orchestrator.orchestrator import Orchestrator
from netcoop.orchestrator.trace import MANIFEST, TRACE, replay
from netcoop.protocol.common import MessageType
from netcoop.protocol.report import ReportStatus
from netcoop.review import Decision, review

REPO = Path(__file__).resolve().parents[1]
EXE = str(Path(sys.executable).with_name("netcoop.exe" if os.name == "nt" else "netcoop"))
T = MessageType


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    adapter = load_adapter()
    out = {}
    for name, fam, seed in [
        ("iface", "interface_fault", 970),
        ("wifi", "weak_wifi", 971),
        ("normal", "normal", 972),
    ]:
        d = tmp_path_factory.mktemp(name)
        adapter.generate(
            scenario=fam, seed=seed, intensity=1.0, noise=0.0, missing_rate=0.0, out_dir=d
        )
        out[name] = d
    return out


# ----------------------------------------------------------------------------- pause / resume
@pytest.mark.parametrize("pause_after", [1, 2])
def test_resume_reproduces_the_uninterrupted_trace(
    runs: dict[str, Path], tmp_path: Path, pause_after: int
) -> None:
    full = Orchestrator().run(runs["iface"], out_dir=tmp_path / "full")
    paused = Orchestrator().run(runs["iface"], out_dir=tmp_path / "p", pause_after=pause_after)
    assert paused.report is None and paused.run_dir is not None
    manifest = json.loads((paused.run_dir / MANIFEST).read_text())
    assert manifest["paused"] and manifest["checkpoint_round"] == pause_after
    resumed = Orchestrator().run(
        runs["iface"], out_dir=tmp_path / "r", resume_from=paused.run_dir / TRACE
    )
    assert resumed.run_dir is not None and full.run_dir is not None
    assert (resumed.run_dir / TRACE).read_bytes() == (full.run_dir / TRACE).read_bytes()
    assert resumed.report == full.report


def test_finished_run_is_not_a_checkpoint(runs: dict[str, Path], tmp_path: Path) -> None:
    done = Orchestrator().run(runs["iface"], out_dir=tmp_path)
    assert done.run_dir is not None
    with pytest.raises(ValueError, match="not a checkpoint"):
        Orchestrator().run(runs["iface"], out_dir=tmp_path / "x", resume_from=done.run_dir / TRACE)


# ----------------------------------------------------------------------------- human review
def test_review_is_recorded_in_the_trace(runs: dict[str, Path], tmp_path: Path) -> None:
    res = Orchestrator().run(runs["iface"], out_dir=tmp_path)
    run = res.run_dir
    assert run is not None and res.report is not None and res.report.recommended_actions
    rec = review(run, [Decision(1, True, "ok"), Decision(2, False)], "Asha N")
    assert [r["approved"] for r in rec] == [True, False] and rec[0]["reviewer"] == "human.asha-n"
    board = replay(run / TRACE)  # verifies the updated manifest hash too
    acks = board.query(type=T.ACK)
    assert len(acks) == 2 and all(board.get(a.causation_id).type is T.REPORT for a in acks)  # type: ignore[union-attr]
    assert review(run, [Decision(1, True, "ok")], "Asha N") == [], (
        "identical decision is idempotent"
    )
    assert "## Human review" in (run / "report.md").read_text()
    with pytest.raises(ValueError, match="does not exist"):
        review(run, [Decision(99, True)], "x")


# ----------------------------------------------------------------------------- extensions
def _overloaded_ap(src: Path, dst: Path) -> None:
    dst.mkdir()
    for f in src.iterdir():
        (dst / f.name).write_bytes(f.read_bytes())
    rows = [json.loads(x) for x in (dst / "telemetry.jsonl").read_text().splitlines()]
    ap = next(r["ap_id"] for r in rows if r["kind"] == "wireless")
    late = set(sorted({r["ts"] for r in rows})[15:])
    for r in rows:
        if r["kind"] == "wireless" and r["ap_id"] == ap and r["ts"] in late:
            r["clients"] = r.get("clients", 12) * 5
            r["retrans_pct"] = r.get("retrans_pct", 4) + 20
    (dst / "telemetry.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def _run_cli(run: Path, out: Path, env: dict[str, str]) -> dict:  # type: ignore[type-arg]
    p = subprocess.run(
        [EXE, "run", str(run), "--out", str(out)],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(next(out.iterdir()).joinpath("report.json").read_text())


def test_new_fault_and_agent_from_data_only(runs: dict[str, Path], tmp_path: Path) -> None:
    _overloaded_ap(runs["normal"], tmp_path / "in")
    plain = _run_cli(tmp_path / "in", tmp_path / "a", {})
    extended = _run_cli(
        tmp_path / "in",
        tmp_path / "b",
        {"NETCOOP_EXTENSIONS": str(REPO / "examples" / "extension")},
    )
    assert "ap_client_overload" not in json.dumps(plain)
    assert "ap_client_overload" in extended["suspected_root_cause"]
    assert "client_load" in extended["evidence_sources"], "the new data-defined agent took part"
    assert (
        extended["status"] != "diagnosed"
        or "ap_client_overload" in extended["suspected_root_cause"]
    )


def test_extensions_cannot_redefine_shipped_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "catalogue").mkdir()
    (tmp_path / "catalogue" / "hypotheses.yaml").write_text("hypotheses:\n  link_congestion: {}\n")
    monkeypatch.setenv("NETCOOP_EXTENSIONS", str(tmp_path))
    with pytest.raises(ValueError, match="redefines"):
        merge_section({"link_congestion": {}}, "catalogue/hypotheses.yaml", "hypotheses")


def test_code_plugin_module_registers_an_agent(tmp_path: Path) -> None:
    (tmp_path / "my_plugin.py").write_text(
        "from netcoop.agents.base import Agent\n"
        "from netcoop.agents.registry import register_agent\n"
        "from netcoop.protocol.capability import AgentRole, CapabilityCard\n"
        "@register_agent\n"
        "class Hello(Agent):\n"
        "    card = CapabilityCard(agent_id='hello', version='1', role=AgentRole.EXTERNAL,\n"
        "                          description='demo', protocol_versions=('2.0',),\n"
        "                          consumes_types=(), produces_types=())\n"
        "    def step(self, inbox, ctx):\n"
        "        pass\n"
    )
    code = "from netcoop.agents.registry import registered; print('hello' in registered())"
    env = {**os.environ, "NETCOOP_PLUGINS": "my_plugin", "PYTHONPATH": str(tmp_path)}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert out.stdout.strip() == "True", out.stderr


# --- MCP and external agents ---
mcp = pytest.importorskip("mcp")


def test_mcp_server_exposes_tools_and_resources() -> None:
    from netcoop.mcp_server import TOOLS, build_server

    server = build_server()
    tools = {t.name for t in asyncio.run(server.list_tools())}
    assert {fn.__name__ for fn in TOOLS} <= tools
    resources = {str(r.uri) for r in asyncio.run(server.list_resources())}
    assert "netcoop://schemas/message" in resources


def test_mcp_tools_end_to_end(runs: dict[str, Path], tmp_path: Path) -> None:
    from netcoop.mcp_server import (
        diagnose,
        get_report,
        get_topology,
        get_trace,
        list_runs,
        review_actions,
        translate,
    )

    out = diagnose(str(runs["iface"]), runs_dir=str(tmp_path))
    inc = out["incident_id"]
    assert out["report"]["status"] in {s.value for s in ReportStatus}
    assert [r["incident_id"] for r in list_runs(str(tmp_path))] == [inc]
    assert get_report(inc, "md", str(tmp_path)).startswith(f"# Incident {inc}")
    assert get_trace(inc, "VERDICT", runs_dir=str(tmp_path))
    assert get_topology(inc, str(tmp_path))["present"]
    assert translate(str(runs["iface"]))["stats"]["series"] > 0
    assert review_actions(inc, approve=[1], reviewer="mcp", runs_dir=str(tmp_path))


def test_external_lite_agent_joins_a_diagnosis(runs: dict[str, Path], tmp_path: Path) -> None:
    """An external probe speaking protocol 1.0 'lite' posts a hypothesis through MCP."""
    from netcoop.mcp_server import diagnose

    gt = json.loads((runs["wifi"] / "ground_truth.json").read_text())
    card = {
        "agent_id": "ext-probe",
        "version": "1.0",
        "role": "external",
        "description": "site survey probe",
        "protocol_versions": ["1.0"],
        "consumes_types": [],
        "produces_types": ["HYPOTHESIS"],
        "hypothesis_types": ["weak_wifi_signal"],
    }
    msg = {
        "protocol": "netcoop",
        "version": "1.0",
        "id": "x1",
        "incident": "external",
        "from": "ext-probe",
        "time": "2026-10-01T09:20:00Z",
        "type": "HYPOTHESIS",
        "payload": {
            "hypothesis": "weak_wifi_signal",
            "entities": [{"id": gt["target_entity"], "type": "access_point"}],
            "confidence_pct": 70,
        },
    }
    out = diagnose(
        str(runs["wifi"]), runs_dir=str(tmp_path), external_card=card, external_messages=[msg]
    )
    trace = [json.loads(x)["msg"] for x in (Path(out["run_dir"]) / TRACE).read_text().splitlines()]
    ext = [m for m in trace if m["sender"] == "ext-probe" and m["type"] == "HYPOTHESIS"]
    assert ext and "1.0->2.0" not in json.dumps(ext[0]), "re-issued natively on the board"
    stances = [
        m
        for m in trace
        if m["type"] in ("SUPPORT", "CONTRADICT")
        and m["payload"]["target_msg_id"] == ext[0]["msg_id"]
    ]
    assert stances, "other agents responded to the external agent's hypothesis"
    assert (
        out["report"]["status"] == "diagnosed"
        and gt["target_entity"] in out["report"]["affected_devices"]
    )
