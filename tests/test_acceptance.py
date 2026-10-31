"""Acceptance gate: every minimum acceptance criterion of problem statement A10, checked.

A10.1 at least two collaborating agents with distinct responsibilities
A10.2 structured communication between agents
A10.3 evidence from multiple agents contributes to a single diagnosis
A10.4 at least one malformed, missing or incompatible input case is handled
A10.5 a report with probable root cause, supporting evidence and recommended action
A10.6 a reproducible run using supplied or documented test data
"""

from __future__ import annotations

from pathlib import Path

import pytest

from netcoop.agents.registry import registered
from netcoop.api import run_diagnosis
from netcoop.generation import load_adapter
from netcoop.mutation import mutate
from netcoop.orchestrator.trace import TRACE, replay
from netcoop.protocol.common import MessageType
from netcoop.protocol.messages import parse_message, to_json
from netcoop.protocol.report import ReportStatus
from netcoop.protocol.schema_export import SCHEMA_DIR

T = MessageType


@pytest.fixture(scope="module")
def incident(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, object]:
    d = tmp_path_factory.mktemp("gate")
    load_adapter().generate(
        scenario="link_congestion", seed=900, intensity=1.0, noise=0.1, missing_rate=0.1, out_dir=d
    )
    return d, run_diagnosis(d, out_dir=tmp_path_factory.mktemp("gate_runs"))


def test_a10_1_two_agents_with_distinct_responsibilities(incident) -> None:  # type: ignore[no-untyped-def]
    reg = registered()
    specialists = {
        k: set(v.card.consumes_metrics) for k, v in reg.items() if v.card.consumes_metrics != ("*",)
    }
    assert len(reg) >= 2 and len(specialists) >= 2
    sets = list(specialists.values())
    assert all(a.isdisjoint(b) for i, a in enumerate(sets) for b in sets[i + 1 :]), (
        "responsibilities overlap"
    )
    _, res = incident
    assert len({m.sender for m in res.board.query(type=T.CLUE)}) >= 2


def test_a10_2_structured_communication(incident) -> None:  # type: ignore[no-untyped-def]
    _, res = incident
    msgs = res.board.messages()
    assert all(parse_message(to_json(m)) == m for m in msgs), (
        "every message is a valid protocol message"
    )
    exchanged = {t for t in (T.REQUEST, T.RESPONSE, T.SUPPORT) if res.board.query(type=t)}
    assert exchanged == {T.REQUEST, T.RESPONSE, T.SUPPORT}, "agents query and answer each other"
    assert (SCHEMA_DIR / "message.json").is_file() and (SCHEMA_DIR.parent / "PROTOCOL.md").is_file()


def test_a10_3_multiple_agents_feed_one_diagnosis(incident) -> None:  # type: ignore[no-untyped-def]
    _, res = incident
    r = res.report
    assert r.status is ReportStatus.DIAGNOSED
    specialists = {e for e in r.evidence_sources if e in registered()}
    assert len(specialists) >= 2, r.evidence_sources
    assert len({p.agent for p in r.x_netcoop.evidence_provenance}) >= 2
    assert len(res.board.query(type=T.REPORT)) == 1


@pytest.mark.parametrize(
    "kind", ["binary_junk", "drop_timestamp_field", "unit_change", "drop_topology"]
)
def test_a10_4_malformed_missing_incompatible_input(incident, tmp_path: Path, kind: str) -> None:  # type: ignore[no-untyped-def]
    src, _ = incident
    mutate(src, tmp_path / "bad", kind, seed=0)
    res = run_diagnosis(tmp_path / "bad", out_dir=None)
    assert res.board.query(type=T.REPORT), "the run completes"
    if kind != "unit_change":  # a recoverable unit change produces no error by design
        assert res.board.query(type=T.ERROR) and res.report.limitations


def test_a10_5_report_has_cause_evidence_action(incident) -> None:  # type: ignore[no-untyped-def]
    _, res = incident
    r = res.report
    assert r.suspected_root_cause and r.supporting_evidence and r.recommended_actions
    assert 0 < r.confidence <= 1


def test_a10_6_reproducible_run(incident, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    src, res = incident
    again = run_diagnosis(src, out_dir=tmp_path)
    assert (again.run_dir / TRACE).read_bytes() == (res.run_dir / TRACE).read_bytes()
    assert replay(res.run_dir / TRACE).version == res.board.version
