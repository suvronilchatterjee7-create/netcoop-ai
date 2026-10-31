"""Phase 4 tests: detection library, calibration, catalogue, specialist and connectivity agents."""

from __future__ import annotations

import ast
import json
import math
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from netcoop.agents.registry import registered
from netcoop.api import run_diagnosis
from netcoop.calibration import calibrate, seed_split
from netcoop.catalogue import get_catalogue, load_specialists
from netcoop.config import get_value, load_config, resolve_key
from netcoop.detection import Detector, mann_kendall, quantile, theil_sen
from netcoop.generation import load_adapter, run_sweep
from netcoop.protocol.common import DataQuality, EntityRef, ErrorCode, MessageType, Statistic
from netcoop.protocol.payloads import CluePayload, HypothesisPayload, ObservationPayload, Point
from netcoop.protocol.vocabulary import get_vocabulary

T = MessageType
REPO = Path(__file__).resolve().parents[1]
FAMILIES = get_value(load_config("generation"), "scenario_families")
Q = DataQuality(score=1, completeness=1, freshness=1, plausibility=1, mapping_certainty=1)


def series(metric: str, values: list[float | str], etype: str = "link") -> ObservationPayload:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    return ObservationPayload(
        entity=EntityRef(entity_id="x", entity_type=etype),
        metric=metric,
        unit=get_vocabulary().metrics[metric].unit,
        quality=Q,
        points=tuple(Point(t=t0 + timedelta(minutes=i), v=v) for i, v in enumerate(values)),
    )


# ----------------------------------------------------------------------------- detection library
def test_trend_statistics() -> None:
    rising = [float(i) + (i % 3) * 0.1 for i in range(20)]
    z, p = mann_kendall(rising)
    assert z > 0 and p < 1e-6
    assert theil_sen(rising) == pytest.approx(1.0, abs=0.1)
    assert mann_kendall([5.0] * 20) == (0.0, 1.0)
    assert quantile([0.0, 10.0], 0.5) == 5.0


def test_band_detects_sustained_shift_but_ignores_spikes() -> None:
    det = Detector()
    base = det.baseline("utilization", "link")
    assert base is not None
    calm = [base.median] * 30
    spike = calm[:]
    spike[-3] = 100.0
    assert not det.evaluate(series("utilization", spike)).significant  # type: ignore[union-attr]
    shifted = calm[:15] + [99.0] * 15
    f = det.evaluate(series("utilization", shifted))
    assert (
        f is not None
        and f.significant
        and f.deviation > 0
        and f.config_key.startswith("baselines.")
    )


def test_in_window_change_adapts_to_noise() -> None:
    det = Detector()
    lvl = det.baseline("latency", "link").median  # type: ignore[union-attr]
    # small but clean step: within the pooled band, yet far beyond this series' own noise
    wiggle = [0.02 * math.sin(i * 1.7) for i in range(30)]  # small, non-degenerate noise
    clean = [lvl + w for w in wiggle[:15]] + [lvl * 1.6 + w for w in wiggle[15:]]
    f = det.evaluate(series("latency", clean))
    assert f is not None and f.significant and f.method == "in_window_change"


def test_cited_threshold_used_without_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    det = Detector()
    monkeypatch.setattr(det, "baselines", {})
    f = det.evaluate(
        series("rssi", [-80.0 + 0.1 * (i % 3) for i in range(30)], etype="access_point")
    )
    assert f is not None and f.significant and f.basis.value == "threshold"
    assert f.config_key == "detection.thresholds.rssi"


def test_enum_and_trend_findings() -> None:
    det = Detector()
    f = det.evaluate(series("device_status", ["up"] * 15 + ["down"] * 15, etype="switch"))
    assert f is not None and f.significant and f.statistic is Statistic.FRACTION
    t = det.trend(series("interface_in_errors", [float(i * 5) for i in range(30)], etype="switch"))
    assert t is not None and t.significant and t.unit == "count/interval"
    assert det.trend(series("latency", [1.0] * 30)) is None, "trend only for configured counters"


# ----------------------------------------------------------------------------- calibration
def test_calibration_writes_justified_baselines(tmp_path: Path) -> None:
    train, hold = seed_split()
    assert set(train).isdisjoint(hold)
    run_sweep(tmp_path / "gen", scenarios=[FAMILIES[0]], seeds=[train[0]])
    out = tmp_path / "cfg"
    out.mkdir()
    calibrate(tmp_path / "gen", out / "baselines.yaml", limit=2)
    cfg = load_config("baselines", out)  # enforces value/unit/rationale/source on every entry
    entry = cfg["baselines"]["utilization"]["link"]
    assert {"median", "mad", "p_low", "p_high", "n"} <= set(entry["value"])
    assert "training seeds" in entry["source"]


def test_calibration_never_uses_holdout_seeds(tmp_path: Path) -> None:
    _, hold = seed_split()
    run_sweep(tmp_path / "gen", scenarios=[FAMILIES[0]], seeds=[hold[0]])
    with pytest.raises(ValueError, match="no 'normal' runs"):
        calibrate(tmp_path / "gen", tmp_path / "b.yaml", limit=1)


# ----------------------------------------------------------------------------- catalogue & cards
def test_catalogue_covers_every_fault_type() -> None:
    cat = get_catalogue()
    vocab = get_vocabulary()
    assert set(cat.hypotheses) == set(vocab.fault_types())
    families = {vocab.hypothesis_types[h].family for h in cat.hypotheses} - {None}
    suite = set(get_value(load_config("generation"), "ambiguity_suite.families"))
    assert families == (set(FAMILIES) | suite) - {"normal", "interop_failure"}
    for h in cat.hypotheses.values():
        for a in h.actions:
            fields = {f.split("}")[0] for f in a.split("{")[1:]}
            assert fields <= {"root", "upstream", "downstream"}, a


def test_agents_registered_from_data() -> None:
    reg = registered()
    specs = load_specialists()
    assert {s.id for s in specs} | {"connectivity"} <= set(reg)
    every = {h for cls in reg.values() for h in cls.card.hypothesis_types}
    assert every == set(get_catalogue().hypotheses), "every fault is proposable by some agent"
    assert reg["wireless_service"].card.optional


AGENT_SOURCES = sorted((REPO / "netcoop" / "agents").glob("*.py"))


@pytest.mark.parametrize("path", AGENT_SOURCES, ids=lambda p: p.name)
def test_agent_code_has_no_hardcoded_terms(path: Path) -> None:
    """No metric names, source field names, device ids or magic numbers in agent code."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    vocab = get_vocabulary()
    forbidden = set(vocab.metrics)
    mapping = (REPO / "data" / "mappings" / "canonical.yaml").read_text(encoding="utf-8")
    forbidden |= {
        line.split(":")[0].strip()
        for line in mapping.splitlines()
        if line.startswith("      ") and ":" in line and "_" in line.split(":")[0]
    }
    named = {
        id(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and all(isinstance(t, ast.Name) and t.id.isupper() for t in n.targets)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value not in forbidden, f"{path.name}: hard-coded term {node.value!r}"
            assert not any(tok in node.value for tok in ("-rtr-", "-srv-", "-dist-", "-acc-")), (
                node.value
            )
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, int | float)
            and not isinstance(node.value, bool)
            and id(node) not in named
        ):
            assert node.value in (0, 1), f"{path.name}:{node.lineno}: magic number {node.value}"


# --- agents on generated data ---
@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    adapter = load_adapter()
    out = {}
    for i, fam in enumerate(f for f in FAMILIES if f != "interop_failure"):
        d = tmp_path_factory.mktemp(fam)
        adapter.generate(
            scenario=fam, seed=40 + i, intensity=1.0, noise=0.0, missing_rate=0.0, out_dir=d
        )
        out[fam] = d
    return out


def _truth(run: Path) -> dict:  # type: ignore[type-arg]
    return json.loads((run / "ground_truth.json").read_text())


def _hypotheses(result) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    out = []
    for m in result.board.query(type=T.HYPOTHESIS):
        p: HypothesisPayload = m.payload
        out.append(
            (
                p.hypothesis_type,
                next(e.entity.entity_id for e in p.entities if e.role.value == "root"),
            )
        )
    return out


@pytest.mark.parametrize("family", [f for f in FAMILIES if f not in ("normal", "interop_failure")])
def test_true_fault_is_proposed_at_true_location(runs: dict[str, Path], family: str) -> None:
    res = run_diagnosis(runs[family], out_dir=None)
    truth = _truth(runs[family])
    vocab = get_vocabulary()
    expected_types = {
        h for h, d in vocab.hypothesis_types.items() if d.family == truth["root_cause"]
    }
    hyps = _hypotheses(res)
    locations = set(truth["affected_entities"]) | {truth.get("service")}
    assert any(t in expected_types and root in locations for t, root in hyps), hyps
    assert res.info.converged and not res.info.failed_agents


def test_normal_operation_raises_no_hypothesis(runs: dict[str, Path]) -> None:
    res = run_diagnosis(runs["normal"], out_dir=None)
    assert _hypotheses(res) == []
    assert all(not m.payload.significant for m in res.board.query(type=T.CLUE))


def test_clues_carry_complete_provenance(runs: dict[str, Path]) -> None:
    res = run_diagnosis(runs["link_congestion"], out_dir=None)
    b = res.board
    clues = b.query(type=T.CLUE)
    assert clues
    for c in clues:
        p: CluePayload = c.payload
        assert c.causation_id in p.source_observation_ids
        for oid in p.source_observation_ids:
            obs = b.get(oid)
            assert obs is not None and obs.type is T.OBSERVATION
            assert obs.payload.metric == p.metric and obs.payload.entity == p.entity
        assert resolve_key(p.comparison.config_key) is not None, p.comparison.config_key


def test_agents_collaborate_across_roles(runs: dict[str, Path]) -> None:
    res = run_diagnosis(runs["link_congestion"], out_dir=None)
    b = res.board
    (hyp,) = [
        m for m in b.query(type=T.HYPOTHESIS) if m.payload.hypothesis_type == "link_congestion"
    ]
    supporters = {
        s.sender for s in b.query(type=T.SUPPORT) if s.payload.target_msg_id == hyp.msg_id
    }
    assert hyp.sender not in supporters and len(supporters) >= 2, supporters
    assert "connectivity" in supporters
    reqs = [r for r in b.query(type=T.REQUEST) if r.causation_id == hyp.msg_id]
    assert reqs and all(
        any(x.payload.request_msg_id == r.msg_id for x in b.query(type=T.RESPONSE)) for r in reqs
    )


def test_service_failure_has_healthy_transport_support(runs: dict[str, Path]) -> None:
    res = run_diagnosis(runs["dns_dhcp_failure"], out_dir=None)
    b = res.board
    hyps = [
        m
        for m in b.query(type=T.HYPOTHESIS)
        if m.payload.hypothesis_type.endswith("_service_failure")
    ]
    assert hyps
    stances = [s for s in b.query(type=T.SUPPORT) if s.payload.target_msg_id == hyps[0].msg_id]
    assert any(s.sender == "performance" for s in stances), (
        "transport-healthy evidence from performance"
    )


def test_missing_topology_degrades_gracefully(runs: dict[str, Path], tmp_path: Path) -> None:
    src = runs["dns_dhcp_failure"]
    for f in src.iterdir():
        if f.name != "topology.json":
            shutil.copy(f, tmp_path / f.name)
    res = run_diagnosis(tmp_path, out_dir=None)
    codes = {m.payload.code for m in res.board.query(type=T.ERROR)}
    assert ErrorCode.MISSING_TOPOLOGY in codes
    assert any(t.endswith("_service_failure") for t, _ in _hypotheses(res)), (
        "service reasoning needs no topology"
    )


def test_optional_wireless_agent_inactive_on_wired_data(tmp_path: Path) -> None:
    rows = "".join(f"{1790845200 + 60 * i},a,b,{20 + i % 3}\n" for i in range(30))
    (tmp_path / "links.csv").write_text("time,src,dst,util_pct\n" + rows)
    res = run_diagnosis(tmp_path, out_dir=None)
    assert res.info.inactive_agents.get("wireless_service") is True
    assert not any("wireless_service" in lim for lim in res.report.limitations)
