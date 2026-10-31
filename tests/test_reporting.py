"""Phase 7 tests: schema-valid A7 reports, traced evidence, generated text, actions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from netcoop.api import run_diagnosis
from netcoop.generation import load_adapter
from netcoop.mutation import mutate
from netcoop.orchestrator.trace import TRACE
from netcoop.protocol.common import (
    ComparisonBasis,
    Direction,
    EntityRef,
    MessageType,
    Statistic,
    TimeWindow,
)
from netcoop.protocol.payloads import CluePayload, Comparison
from netcoop.protocol.report import Report, ReportStatus
from netcoop.reporting.reporter import interpret

A7_KEYS = {
    "incident_id",
    "status",
    "suspected_root_cause",
    "confidence",
    "affected_devices",
    "supporting_evidence",
    "alternative_causes",
    "recommended_actions",
    "evidence_sources",
    "limitations",
}
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def clue(
    statistic: Statistic,
    value: float,
    unit: str,
    significant: bool = True,
    method: str = "cited_threshold",
    metric: str = "latency",
) -> CluePayload:
    return CluePayload(
        entity=EntityRef(
            entity_id="L1", entity_type="link" if metric != "interface_in_errors" else "switch"
        ),
        metric=metric,
        statistic=statistic,
        value=value,
        unit=unit,
        comparison=Comparison(
            basis=ComparisonBasis.THRESHOLD,
            reference_value=150.0,
            config_key="detection.k",
            method=method,
        ),
        direction=Direction.ABOVE,
        deviation=0.4,
        deviation_unit="relative_to_threshold",
        significant=significant,
        persistence=0.8,
        window=TimeWindow(start=T0, end=T0),
        source_observation_ids=("o1",),
        data_quality=0.9,
    )


def test_interpretations_are_generated_from_the_evidence_model() -> None:
    s = interpret(clue(Statistic.MEDIAN, 210.0, "ms"), "deviates", "link_congestion")
    for part in (
        "latency on L1",
        "210 ms",
        "above",
        "cited threshold of 150 ms",
        "80%",
        "detection.k",
        "0.90",
    ):
        assert part in s, (part, s)
    n = interpret(
        clue(Statistic.MEDIAN, 10.0, "ms", significant=False), "normal", "dns_service_failure"
    )
    assert "stayed normal" in n and "dns_service_failure predicts" in n
    t = interpret(
        clue(Statistic.SLOPE, 3.5, "count/interval", metric="interface_in_errors"), "deviates", "x"
    )
    assert "rising by 3.5 count/interval" in t
    f = interpret(
        clue(Statistic.FRACTION, 0.6, "ratio", metric="interface_in_errors"), "deviates", "x"
    )
    assert "abnormal state in 60%" in f


SPECS = {
    "congestion": ("link_congestion", 310, 1.0, 0.1, 0.1),
    "wifi": ("weak_wifi", 311, 1.0, 0.0, 0.0),
    "dns": ("dns_dhcp_failure", 312, 1.0, 0.1, 0.0),
    "normal": ("normal", 313, 1.0, 0.1, 0.1),
    "interop": ("interop_failure", 314, 1.0, 0.0, 0.1),
    "hardware": ("hardware_failure", 315, 1.0, 0.0, 0.0),
    "faint": ("weak_wifi", 316, 0.25, 0.25, 0.3),
}


@pytest.fixture(scope="module")
def results(tmp_path_factory: pytest.TempPathFactory) -> dict[str, tuple[Path, object]]:
    adapter = load_adapter()
    out: dict[str, tuple[Path, object]] = {}
    for name, (fam, seed, inten, noise, miss) in SPECS.items():
        d = tmp_path_factory.mktemp(name)
        adapter.generate(
            scenario=fam, seed=seed, intensity=inten, noise=noise, missing_rate=miss, out_dir=d
        )
        out[name] = (d, run_diagnosis(d, out_dir=tmp_path_factory.mktemp(f"{name}_runs")))
    mutated = tmp_path_factory.mktemp("mutated")
    mutate(out["congestion"][0], mutated / "run", "type_corruption", seed=1)
    out["mutated"] = (
        mutated / "run",
        run_diagnosis(mutated / "run", out_dir=tmp_path_factory.mktemp("m_runs")),
    )
    return out


@pytest.mark.parametrize("name", [*SPECS, "mutated"])
def test_every_report_is_schema_valid_a7(results, name: str) -> None:  # type: ignore[no-untyped-def]
    _, res = results[name]
    raw = json.loads((res.run_dir / "report.json").read_text())
    assert set(raw) == A7_KEYS | {"x_netcoop"}
    report = Report.model_validate(raw)
    assert report == res.report
    assert all(set(e) == {"metric", "value", "interpretation"} for e in raw["supporting_evidence"])
    assert 0.0 <= report.confidence <= 1.0
    assert report.recommended_actions and not any(
        "{" in a or "}" in a for a in report.recommended_actions
    )
    assert (res.run_dir / "report.md").read_text().startswith(f"# Incident {report.incident_id}")


@pytest.mark.parametrize("name", [*SPECS, "mutated"])
def test_every_evidence_item_traces_to_observations(results, name: str) -> None:  # type: ignore[no-untyped-def]
    _, res = results[name]
    trace = [json.loads(line)["msg"] for line in (res.run_dir / TRACE).read_text().splitlines()]
    by_id = {m["msg_id"]: m for m in trace}
    report = res.report
    prov = report.x_netcoop.evidence_provenance
    assert [p.evidence_index for p in prov] == list(range(len(report.supporting_evidence)))
    for p, item in zip(prov, report.supporting_evidence, strict=True):
        clue_msg = by_id[p.clue_id]
        assert clue_msg["type"] == "CLUE" and clue_msg["sender"] == p.agent
        assert (
            clue_msg["payload"]["metric"] == item.metric
            and clue_msg["payload"]["value"] == item.value
        )
        assert p.observation_ids and all(
            by_id[o]["type"] == "OBSERVATION" for o in p.observation_ids
        )
        assert p.config_key in item.interpretation


def test_diagnosed_report_contents(results) -> None:  # type: ignore[no-untyped-def]
    _, res = results["congestion"]
    r = res.report
    assert r.status is ReportStatus.DIAGNOSED
    root = r.suspected_root_cause.split(" at ")[1].split(":")[0]
    assert r.affected_devices[0] == root
    assert any(root in a for a in r.recommended_actions)
    x = r.x_netcoop
    assert x.score_breakdown and x.score_breakdown[0].term.startswith("prior")
    assert x.simulated_remediation and all(not s.applied for s in x.simulated_remediation)
    assert {"correlator", "performance"} <= set(r.evidence_sources)


def test_abstention_asserts_nothing(results) -> None:  # type: ignore[no-untyped-def]
    _, res = results["hardware"]
    r = res.report
    assert r.status is ReportStatus.INSUFFICIENT_EVIDENCE
    assert r.confidence == 0.0 and r.x_netcoop.confidence_category == "none"
    assert len(r.alternative_causes) >= 2, "both contenders reported"
    assert any(a.startswith("Collect: ") for a in r.recommended_actions)
    assert any(a.startswith("If ") for a in r.recommended_actions)
    assert any("courtroom deferred" in lim for lim in r.limitations)
    assert r.x_netcoop.courtroom and r.x_netcoop.courtroom.outcome == "deferred"


def test_no_fault_report(results) -> None:  # type: ignore[no-untyped-def]
    _, res = results["normal"]
    r = res.report
    if r.status is ReportStatus.NO_FAULT_DETECTED:
        assert r.confidence > 0 and r.recommended_actions and not r.affected_devices


def test_data_problems_reach_limitations(results) -> None:  # type: ignore[no-untyped-def]
    _, res = results["mutated"]
    assert any("TYPE_MISMATCH" in lim for lim in res.report.limitations)
    _, interop = results["interop"]
    assert interop.report.x_netcoop.data_quality is not None


def test_reports_are_deterministic(results, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    d, first = results["dns"]
    again = run_diagnosis(d, out_dir=tmp_path)
    assert again.report.model_dump_json() == first.report.model_dump_json()
    assert (again.run_dir / "report.md").read_text() == (first.run_dir / "report.md").read_text()


def test_report_message_on_board(results) -> None:  # type: ignore[no-untyped-def]
    _, res = results["wifi"]
    (msg,) = res.board.query(type=MessageType.REPORT)
    assert msg.payload.report == res.report
    assert res.board.get(msg.causation_id).type is MessageType.VERDICT  # type: ignore[union-attr]
