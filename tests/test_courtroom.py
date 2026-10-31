"""Phase 6 tests: trigger, rubric, resolve-or-defer, deterministic transcript."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from netcoop.catalogue import Element, get_catalogue
from netcoop.config import get_value, load_config
from netcoop.correlation.fit import load_model, truth_locations
from netcoop.courtroom.courtroom import DEFENSE, JUDGE, PROSECUTOR, _conflicting, _same_prediction
from netcoop.generation import load_adapter
from netcoop.orchestrator.orchestrator import Orchestrator
from netcoop.protocol.common import Decision, MessageType
from netcoop.protocol.report import ReportStatus
from netcoop.protocol.vocabulary import get_vocabulary

T = MessageType
COURT = {PROSECUTOR, DEFENSE, JUDGE}


def el(metric: str, expect: str = "deviates", direction: str = "above") -> Element:
    return Element(
        metric=metric, expect=expect, direction=direction, scope="root", role="supporting"
    )  # type: ignore[arg-type]


def test_prediction_relations() -> None:
    assert _same_prediction(el("packet_loss"), el("packet_loss"))
    assert not _same_prediction(
        el("interface_in_errors", direction="rising"), el("interface_in_errors")
    )
    assert not _same_prediction(el("rssi", direction="below"), el("rssi"))
    assert _conflicting(el("utilization", "normal"), el("utilization"))
    assert not _conflicting(el("utilization", "normal"), el("utilization", direction="rising"))


@pytest.fixture(scope="module")
def model():  # type: ignore[no-untyped-def]
    m = load_model()
    if m is None:
        pytest.skip("correlation model not fitted")
    return m


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    adapter = load_adapter()
    out = {}
    for name, fam, seed in [
        ("if_uplink", "interface_fault", 102),
        ("if_edge", "interface_fault", 104),
        ("hw_switch", "hardware_failure", 103),
        ("hw_ap", "hardware_failure", 100),
        ("congestion", "link_congestion", 105),
    ]:
        d = tmp_path_factory.mktemp(name)
        adapter.generate(
            scenario=fam, seed=seed, intensity=1.0, noise=0.0, missing_rate=0.0, out_dir=d
        )
        out[name] = d
    return out


def _wrong(run: Path, report) -> bool:  # type: ignore[no-untyped-def]
    if report.status is ReportStatus.INSUFFICIENT_EVIDENCE:
        return False
    gt = json.loads((run / "ground_truth.json").read_text())
    vocab = get_vocabulary()
    hyp = report.suspected_root_cause.split(" at ")[0]
    ok = (
        vocab.hypothesis_types.get(hyp) is not None
        and vocab.hypothesis_types[hyp].family == gt["root_cause"]
    )
    return not (ok and set(report.affected_devices) & truth_locations(gt))


def _court(res):  # type: ignore[no-untyped-def]
    return [m for m in res.board.messages() if m.sender in COURT and m.type is not T.CAPABILITY]


@pytest.mark.parametrize("name", ["if_uplink", "if_edge", "hw_switch", "hw_ap"])
def test_courtroom_resolves_or_defers_never_wrong(model, runs: dict[str, Path], name: str) -> None:  # type: ignore[no-untyped-def]
    res = Orchestrator().run(runs[name])
    final = res.board.query(type=T.VERDICT)[-1].payload
    assert final.method == "courtroom", (
        "IF vs hardware_failure is adjudicated (hardware_failure is untrained)"
    )
    assert not _wrong(runs[name], res.report), res.report.suspected_root_cause
    assert any(r.startswith("ruling:") for r in final.rationale)


def test_interface_faults_are_confirmed(model, runs: dict[str, Path]) -> None:  # type: ignore[no-untyped-def]
    for name in ("if_uplink", "if_edge"):
        res = Orchestrator().run(runs[name])
        assert res.report.status is ReportStatus.DIAGNOSED
        assert "confirmed" in res.board.query(type=T.VERDICT)[-1].payload.rationale[-1]


def test_hardware_failures_are_no_longer_misdiagnosed(model, runs: dict[str, Path]) -> None:  # type: ignore[no-untyped-def]
    for name in ("hw_switch", "hw_ap"):
        res = Orchestrator().run(runs[name])
        assert not _wrong(runs[name], res.report)
        assert (
            res.report.x_netcoop
            and res.report.x_netcoop.courtroom
            and res.report.x_netcoop.courtroom.invoked
        )


def test_transcript_is_complete_and_causally_linked(model, runs: dict[str, Path]) -> None:  # type: ignore[no-untyped-def]
    res = Orchestrator().run(runs["hw_switch"])
    b = res.board
    prelim, final = b.query(type=T.VERDICT)
    assert prelim.sender == "correlator" and final.sender == JUDGE
    assert final.causation_id == prelim.msg_id
    rationale = " ".join(final.payload.rationale)
    assert (
        "prosecutor for" in rationale and "defense for" in rationale and "contenders:" in rationale
    )
    stances = [m for m in _court(res) if m.type in (T.SUPPORT, T.CONTRADICT)]
    assert stances and all(b.get(m.payload.target_msg_id).type is T.HYPOTHESIS for m in stances)  # type: ignore[union-attr]
    summary = res.report.x_netcoop.courtroom  # type: ignore[union-attr]
    assert summary and set(summary.transcript_msg_ids) == {m.msg_id for m in _court(res)}
    assert summary.rounds <= int(get_value(load_config("courtroom"), "judge.max_rounds"))


def test_transcript_is_deterministic(model, runs: dict[str, Path]) -> None:  # type: ignore[no-untyped-def]
    a = [m.msg_id for m in _court(Orchestrator().run(runs["if_uplink"]))]
    b = [m.msg_id for m in _court(Orchestrator().run(runs["if_uplink"]))]
    assert a and a == b


def test_courtroom_not_opened_without_a_contender(model, runs: dict[str, Path]) -> None:  # type: ignore[no-untyped-def]
    res = Orchestrator().run(runs["congestion"])
    (verdict,) = res.board.query(type=T.VERDICT)
    assert verdict.payload.method != "courtroom" and verdict.payload.decision is Decision.DIAGNOSED
    assert not _court(res)


def test_courtroom_can_be_disabled(model, runs: dict[str, Path]) -> None:  # type: ignore[no-untyped-def]
    res = Orchestrator(courtroom=False).run(runs["hw_ap"])
    assert len(res.board.query(type=T.VERDICT)) == 1 and not _court(res)


def test_catalogue_relations_used_by_the_trigger() -> None:
    cat = get_catalogue()
    assert "hardware_failure" in cat.hypotheses["interface_fault"].competes_with
    assert "interface_fault" in cat.hypotheses["hardware_failure"].explains
