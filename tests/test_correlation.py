"""Phase 5 tests: evidence model, calibration, decision policy and degraded-evidence abstention."""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pytest

from netcoop.api import run_diagnosis
from netcoop.catalogue import get_catalogue
from netcoop.correlation.correlator import Correlator, category
from netcoop.correlation.features import Candidate, Context
from netcoop.correlation.fit import calibration_metrics, load_model, truth_locations
from netcoop.correlation.model import Model, decide, fit_platt, fit_tables
from netcoop.generation import load_adapter
from netcoop.mutation import mutate
from netcoop.protocol.common import Decision, MessageType
from netcoop.protocol.report import ReportStatus
from netcoop.protocol.vocabulary import get_vocabulary

T = MessageType
CAT = get_catalogue()
H = "link_congestion"
N_EL = len(CAT.hypotheses[H].signature)


def rec(
    true: bool, first: str, analytic: str = "none", quality: float = 0.9, type_: str = H
) -> dict:  # type: ignore[type-arg]
    n = len(CAT.hypotheses[type_].signature)
    return {
        "type": type_,
        "statuses": [first] + ["unknown"] * (n - 1),
        "analytic": analytic,
        "quality": quality,
        "true": true,
    }


# ----------------------------------------------------------------------------- estimation
def test_likelihood_ratios_follow_the_data() -> None:
    data = [rec(True, "satisfied", "support") for _ in range(40)] + [
        rec(False, "violated", "contradict") for _ in range(40)
    ]
    t = fit_tables(data, CAT, alpha=1.0, k=20.0, qcut=[0.5])
    el = t["types"][H]["elements"][0]
    assert el["satisfied"] > 0 > el["violated"]
    assert t["analytic"]["support"] > 0 > t["analytic"]["contradict"]


def test_faults_without_examples_fall_back_to_pooled_rates() -> None:
    data = [rec(True, "satisfied") for _ in range(30)] + [rec(False, "violated") for _ in range(30)]
    t = fit_tables(data, CAT, alpha=1.0, k=20.0, qcut=[])
    other = t["types"]["device_overload"]
    assert other["n_true"] == other["n_false"] == 0
    # its first element is (required, deviates) like congestion's:
    # pooled evidence still points the right way
    assert other["elements"][0]["satisfied"] > 0


def test_platt_is_monotone_and_calibrates() -> None:
    scores = [x / 10 for x in range(-50, 51)]
    labels = [s + 0.3 * math.sin(i) > 0 for i, s in enumerate(scores)]
    a, b = fit_platt(scores, labels, l2=1e-3)
    assert a > 0
    assert 1 / (1 + math.exp(-(a * 4 + b))) > 0.9 > 0.1 > 1 / (1 + math.exp(-(a * -4 + b)))


def test_calibration_metrics() -> None:
    perfect = [(1.0, True), (0.0, False)] * 10
    m = calibration_metrics(perfect, 10)
    assert m["brier"] == 0 and m["ece"] == 0
    over = [(0.9, False)] * 10
    assert calibration_metrics(over, 10)["ece"] == pytest.approx(0.9)


# ----------------------------------------------------------------------------- decision policy
def _model(**kw: object) -> Model:
    data = [rec(True, "satisfied", "support") for _ in range(40)] + [
        rec(False, "violated") for _ in range(40)
    ]
    m = Model(fit_tables(data, CAT, 1.0, 20.0, []), [])
    m.platt = fit_platt([m.score(r) for r in data], [r["true"] for r in data], 1e-3)
    m.accept, m.margin, m.normal_accept = 0.8, 2.0, 0.7
    m.normal_quality_cutoffs, m.significant_edges, m.normal_table = (
        [],
        [0, 1],
        {"0,0": 0.9, "0,1": 0.3},
    )
    for k, v in kw.items():
        setattr(m, k, v)
    return m


def _cand(root: str, first: str, analytic: str = "none", type_: str = H) -> Candidate:
    n = len(CAT.hypotheses[type_].signature)
    return Candidate(
        type_,
        root,
        "link",
        [f"h-{root}"],
        ["p"],
        (),
        (first,) + ("unknown",) * (n - 1),
        (),
        analytic,
        (),
        0.9,
    )


def never(_a: Candidate, _b: Candidate) -> bool:
    return False


def test_clear_winner_is_diagnosed() -> None:
    out = decide(
        [_cand("L1", "satisfied", "support"), _cand("L2", "violated")],
        Context(),
        _model(),
        CAT,
        never,
    )
    assert out.decision == "diagnosed" and out.winner and out.winner.candidate.root == "L1"


def test_near_tie_is_flagged_not_guessed() -> None:
    out = decide(
        [_cand("L1", "satisfied", "support"), _cand("L2", "satisfied", "support")],
        Context(),
        _model(),
        CAT,
        never,
    )
    assert out.decision == "insufficient_evidence" and out.near_tie and out.winner is None


def test_causal_precedence_merges_explained_effect() -> None:
    a, b = _cand("L1", "satisfied", "support"), _cand("L2", "satisfied", "support")
    out = decide([a, b], Context(), _model(), CAT, lambda x, y: (x.root, y.root) == ("L1", "L2"))
    assert out.decision == "diagnosed" and out.winner and out.winner.candidate.root == "L1"
    assert next(r for r in out.ranking if r.candidate.root == "L2").merged_into == a.key


def test_no_fault_requires_assessable_faults_and_quiet_data() -> None:
    m = _model()
    assert decide([], Context(n_significant=0), m, CAT, never).decision == "no_fault_detected"
    assert decide([], Context(n_significant=5), m, CAT, never).decision == "insufficient_evidence"
    blind = decide([], Context(n_significant=0, unassessable=["weak_wifi_signal"]), m, CAT, never)
    assert blind.decision == "insufficient_evidence"
    assert any("weak_wifi_signal" in x for x in blind.missing_evidence)


def test_confidence_categories() -> None:
    assert [category(p, 0.9, 0.5) for p in (0.95, 0.6, 0.2)] == ["high", "medium", "low"]


# --- with the fitted model ---
@pytest.fixture(scope="module")
def fitted() -> Model:
    m = load_model()
    if m is None:
        pytest.skip("config/correlation.yaml not fitted; run `netcoop fit`")
    return m


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    adapter = load_adapter()
    specs = {
        "congestion": ("link_congestion", 71, 1.0, 0.0, 0.0),
        "dns": ("dns_dhcp_failure", 72, 1.0, 0.0, 0.0),
        "normal": ("normal", 73, 1.0, 0.0, 0.0),
        "degraded": ("weak_wifi", 74, 0.25, 0.25, 0.3),
    }
    out = {}
    for name, (fam, seed, inten, noise, miss) in specs.items():
        d = tmp_path_factory.mktemp(name)
        adapter.generate(
            scenario=fam, seed=seed, intensity=inten, noise=noise, missing_rate=miss, out_dir=d
        )
        out[name] = d
    return out


def _correct(run: Path, report) -> bool:  # type: ignore[no-untyped-def]
    gt = json.loads((run / "ground_truth.json").read_text())
    if report.status is ReportStatus.NO_FAULT_DETECTED:
        return gt["root_cause"] == "normal"
    v = get_vocabulary()
    return any(d in truth_locations(gt) for d in report.affected_devices) and any(
        v.hypothesis_types[h].family == gt["root_cause"]
        for h in v.hypothesis_types
        if h in report.suspected_root_cause
    )


@pytest.mark.parametrize("name", ["congestion", "dns"])
def test_clear_faults_are_diagnosed_correctly(
    fitted: Model, runs: dict[str, Path], name: str
) -> None:
    res = run_diagnosis(runs[name], out_dir=None)
    (verdict,) = res.board.query(type=T.VERDICT)
    assert verdict.payload.decision is Decision.DIAGNOSED, verdict.payload.rationale
    assert verdict.payload.confidence_category == "high"
    assert res.report.status is ReportStatus.DIAGNOSED and _correct(runs[name], res.report)


def test_clean_normal_operation_is_not_called_a_fault(fitted: Model, runs: dict[str, Path]) -> None:
    res = run_diagnosis(runs["normal"], out_dir=None)
    assert res.report.status in (ReportStatus.NO_FAULT_DETECTED, ReportStatus.INSUFFICIENT_EVIDENCE)


def test_degraded_evidence_never_produces_a_wrong_claim(
    fitted: Model, runs: dict[str, Path]
) -> None:
    res = run_diagnosis(runs["degraded"], out_dir=None)
    if res.report.status is not ReportStatus.INSUFFICIENT_EVIDENCE:
        assert _correct(runs["degraded"], res.report), res.report.suspected_root_cause


def test_missing_required_metric_blocks_a_no_fault_claim(
    fitted: Model, runs: dict[str, Path], tmp_path: Path
) -> None:
    """Dropping a metric a fault needs makes it unassessable: 'no fault' must not be claimed."""
    src = runs["normal"]
    dst = tmp_path / "run"
    shutil.copytree(src, dst)
    lines = (dst / "telemetry.jsonl").read_text().splitlines()
    kept = [
        json.dumps({k: v for k, v in json.loads(x).items() if k != "utilization_pct"})
        for x in lines
    ]
    (dst / "telemetry.jsonl").write_text("\n".join(kept) + "\n")
    res = run_diagnosis(dst, out_dir=None)
    assert res.report.status is ReportStatus.INSUFFICIENT_EVIDENCE
    (verdict,) = res.board.query(type=T.VERDICT)
    assert any("link_congestion" in x for x in verdict.payload.missing_evidence)


@pytest.mark.parametrize(
    "kind", ["binary_junk", "drop_timestamp_field", "type_corruption", "drop_topology"]
)
def test_mutated_input_never_yields_a_wrong_claim(
    fitted: Model, runs: dict[str, Path], tmp_path: Path, kind: str
) -> None:
    mutate(runs["congestion"], tmp_path / "m", kind, seed=0)
    res = run_diagnosis(tmp_path / "m", out_dir=None)
    if res.report.status is not ReportStatus.INSUFFICIENT_EVIDENCE:
        assert _correct(runs["congestion"], res.report), (kind, res.report.suspected_root_cause)
    assert res.report.limitations, "data problems must be reported"


def test_correlator_without_model_abstains(runs: dict[str, Path]) -> None:
    from netcoop.orchestrator.orchestrator import Orchestrator

    c = Correlator()
    c.model = None
    res = Orchestrator(correlator=c).run(runs["congestion"])
    (verdict,) = res.board.query(type=T.VERDICT)
    assert verdict.payload.decision is Decision.INSUFFICIENT_EVIDENCE
    assert "model_not_fitted" in verdict.payload.rationale[0]
