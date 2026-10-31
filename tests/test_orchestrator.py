"""Phase 3 tests: case board, orchestrator rounds, routing, isolation, tracing, replay."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from netcoop.agents.registry import create_agents, registered
from netcoop.api import diagnose, run_diagnosis
from netcoop.board.board import Board
from netcoop.generation import load_adapter
from netcoop.orchestrator.orchestrator import Event, Orchestrator
from netcoop.orchestrator.trace import TRACE, ReplayError, replay
from netcoop.protocol.common import ErrorCode, MessageType
from netcoop.protocol.payloads import AckStatus, ResponsePayload, ResponseStatus
from netcoop.protocol.report import Report, ReportStatus
from tests import board_agents as ba
from tests import protocol_factories as pf

T = MessageType


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("congestion")
    load_adapter().generate(
        scenario="link_congestion", seed=21, intensity=1.0, noise=0.0, missing_rate=0.0, out_dir=d
    )
    return d


def errors(result, code: ErrorCode) -> list:  # type: ignore[no-untyped-def,type-arg]
    return [m for m in result.board.query(type=T.ERROR) if m.payload.code is code]


# ----------------------------------------------------------------------------- board
def _board() -> Board:
    return Board(pf.INCIDENT, max_depth=3, per_agent_round_budget=2)


def test_board_enforces_idempotency_causality_depth_and_budget() -> None:
    b = _board()
    obs = pf.message(T.OBSERVATION)
    assert b.post(obs, 0) == (AckStatus.ACCEPTED, "")
    assert b.post(obs, 0)[0] is AckStatus.DUPLICATE
    orphan = pf.message(T.CLUE, parent=pf.message(T.ACK))
    assert b.post(orphan, 1)[0] is AckStatus.REJECTED
    other = pf.message(T.ACK).model_copy(update={"correlation_id": "elsewhere"})
    assert b.post(other, 1)[0] is AckStatus.REJECTED
    c1 = pf.message(T.CLUE, parent=obs)
    h = pf.message(T.HYPOTHESIS, parent=c1)
    s = pf.message(T.SUPPORT, parent=h)
    r = pf.message(T.REQUEST, parent=s)  # depth 4 > 3
    assert [b.post(m, 1)[0] for m in (c1, h)] == [AckStatus.ACCEPTED] * 2
    assert b.post(s, 1)[0] is AckStatus.REJECTED, "budget of 2 posts per agent per round"
    assert b.post(s, 2)[0] is AckStatus.ACCEPTED
    status, reason = b.post(r, 3)
    assert status is AckStatus.REJECTED and "depth" in reason
    assert len(b.rejections) == 4 and b.duplicates == 1
    assert [m.msg_id for m in b.ancestors(s.msg_id)] == [obs.msg_id, c1.msg_id, h.msg_id, s.msg_id]


def test_board_queries_and_subscriptions() -> None:
    b = Board(pf.INCIDENT, 10, 100)
    seen: list[str] = []
    b.subscribe(lambda e: seen.append(e.msg.msg_id), types=[T.CLUE], entity=pf.LINK.entity_id)
    obs = pf.message(T.OBSERVATION)
    clue = pf.message(T.CLUE, parent=obs)
    for m in (obs, clue, pf.message(T.ACK)):
        b.post(m, 0)
    assert seen == [clue.msg_id]
    assert b.query(metric="utilization") == [obs, clue]
    assert b.query(entity=pf.LINK.entity_id, type=T.CLUE) == [clue]
    assert b.version == 3 and b.counts() == {"ACK": 1, "CLUE": 1, "OBSERVATION": 1}


# ----------------------------------------------------------------------------- exchange
def test_multi_round_request_response_support(run_dir: Path) -> None:
    det = ba.Detector()
    res = run_diagnosis(run_dir, out_dir=None, orchestrator=Orchestrator([det, ba.Infra()]))
    b = res.board
    assert res.info.converged and res.info.rounds >= 3
    (hyp,) = b.query(type=T.HYPOTHESIS)
    (req,) = b.query(type=T.REQUEST)
    (resp,) = b.query(type=T.RESPONSE)
    (sup,) = b.query(type=T.SUPPORT)
    rounds = {m.msg_id: b.entry(m.msg_id).round for m in (hyp, req, resp, sup)}  # type: ignore[union-attr]
    assert rounds[hyp.msg_id] == rounds[req.msg_id] < rounds[resp.msg_id] == rounds[sup.msg_id]
    assert resp.recipient == det.agent_id and resp.sender == "t-infra"
    assert isinstance(resp.payload, ResponsePayload) and resp.payload.status is ResponseStatus.OK
    assert det.responses == [resp], "directed RESPONSE delivered only to the requester"
    assert sup.payload.target_msg_id == hyp.msg_id  # type: ignore[union-attr]
    chain = [m.type for m in b.ancestors(sup.msg_id)]
    assert chain == [T.OBSERVATION, T.CLUE, T.HYPOTHESIS, T.REQUEST, T.SUPPORT]
    assert b.query(type=T.VERDICT) and b.query(type=T.REPORT)


def test_unservable_request_gets_unsupported_response(run_dir: Path) -> None:
    res = run_diagnosis(
        run_dir,
        out_dir=None,
        orchestrator=Orchestrator([ba.Detector(capability="analysis:nobody_does_this")]),
    )
    (resp,) = res.board.query(type=T.RESPONSE)
    assert resp.sender == "orchestrator" and resp.payload.status is ResponseStatus.UNSUPPORTED  # type: ignore[union-attr]


# ----------------------------------------------------------------------------- isolation
def test_agent_crash_is_isolated_and_reported(run_dir: Path) -> None:
    res = run_diagnosis(
        run_dir, out_dir=None, orchestrator=Orchestrator([ba.Crasher(), ba.Detector(), ba.Infra()])
    )
    assert "t-crasher" in res.info.failed_agents
    (err,) = errors(res, ErrorCode.AGENT_FAILURE)
    assert "simulated agent bug" in err.payload.message  # type: ignore[union-attr]
    assert not res.board.query(sender="t-crasher", type=T.CLUE), (
        "output of a failed step is discarded"
    )
    assert res.board.query(type=T.SUPPORT), "other agents unaffected"
    assert any("t-crasher" in lim for lim in res.report.limitations)


def test_agent_timeout_is_isolated(run_dir: Path) -> None:
    t0 = time.monotonic()
    res = run_diagnosis(
        run_dir,
        out_dir=None,
        orchestrator=Orchestrator([ba.Sleeper(3.0), ba.Detector(), ba.Infra()], timeout_s=0.5),
    )
    assert time.monotonic() - t0 < 3.0, "orchestrator must not wait for a hung agent"
    assert errors(res, ErrorCode.AGENT_TIMEOUT) and "t-sleeper" in res.info.failed_agents
    assert not res.board.query(sender="t-sleeper", type=T.CLUE)
    assert res.board.query(type=T.SUPPORT)


def test_loops_are_bounded(run_dir: Path) -> None:
    res = run_diagnosis(
        run_dir,
        out_dir=None,
        orchestrator=Orchestrator([ba.Looper("t-ping", True), ba.Looper("t-pong", False)]),
    )
    assert res.board.query(type=T.REPORT), "run terminates"
    assert errors(res, ErrorCode.BUDGET_EXCEEDED)
    depths = [m.depth for m in res.board.query(type=T.SUPPORT)]
    assert max(depths) <= Orchestrator().max_depth


def test_flooding_agent_is_capped(run_dir: Path) -> None:
    orch = Orchestrator([ba.Flooder(50)])
    orch.budget = 10
    res = orch.run(run_dir)
    assert len(res.board.query(sender="t-flooder", type=T.CLUE)) == 10
    assert len(res.board.query(type=T.OBSERVATION)) == len(res.translation.observations), (
        "ingestion not capped"
    )
    (err,) = errors(res, ErrorCode.BUDGET_EXCEEDED)
    assert err.payload.context["count"] == 41  # type: ignore[union-attr]


def test_inactive_and_incompatible_agents(run_dir: Path) -> None:
    res = run_diagnosis(
        run_dir,
        out_dir=None,
        orchestrator=Orchestrator(
            [ba.Dormant(optional=True), ba.Dormant(optional=False), ba.LiteOnly()]
        ),
    )
    assert res.info.inactive_agents == {"t-dormant-opt": True, "t-dormant-req": False}
    assert errors(res, ErrorCode.INCOMPATIBLE_VERSION)
    lims = " ".join(res.report.limitations)
    assert "t-dormant-req" in lims and "t-dormant-opt" not in lims and "t-lite" in lims


# ----------------------------------------------------------------------------- trace & replay
def test_trace_is_deterministic_and_replays(run_dir: Path, tmp_path: Path) -> None:
    def go(out: Path):  # type: ignore[no-untyped-def]
        return run_diagnosis(
            run_dir, out_dir=out, orchestrator=Orchestrator([ba.Detector(), ba.Infra()])
        )

    a, b = go(tmp_path / "a"), go(tmp_path / "b")
    assert a.run_dir and b.run_dir
    ta, tb = (a.run_dir / TRACE).read_bytes(), (b.run_dir / TRACE).read_bytes()
    assert ta == tb, "same input + config => identical trace"
    board = replay(a.run_dir / TRACE)
    assert [m.msg_id for m in board.messages()] == [m.msg_id for m in a.board.messages()]
    assert (a.run_dir / "manifest.json").is_file()
    Report.model_validate_json((a.run_dir / "report.json").read_text())

    lines = ta.decode().splitlines()
    tampered = tmp_path / "t" / TRACE
    tampered.parent.mkdir()
    tampered.write_text("\n".join(lines[:-2] + [lines[-1]]) + "\n")
    with pytest.raises(ReplayError):
        replay(tampered)


def test_event_hook_sees_every_message(run_dir: Path) -> None:
    events: list[Event] = []
    res = run_diagnosis(
        run_dir,
        out_dir=None,
        on_event=events.append,
        orchestrator=Orchestrator([ba.Detector(), ba.Infra()]),
    )
    assert sum(e.kind == "message" for e in events) == res.board.version
    assert events[-1].kind == "done"
    assert [e.kind for e in events if e.kind in ("stage",)] == ["stage", "stage"]


# ----------------------------------------------------------------------------- API & registry
def test_api_without_specialists_abstains_honestly(run_dir: Path) -> None:
    report = diagnose(run_dir, out_dir=None, orchestrator=Orchestrator([]))
    assert report.status is ReportStatus.INSUFFICIENT_EVIDENCE
    assert report.confidence == 0.0


def test_registry_creates_fresh_instances() -> None:
    a, b = create_agents(), create_agents()
    assert [x.agent_id for x in a] == sorted(registered())
    assert all(x is not y for x, y in zip(a, b, strict=True))
