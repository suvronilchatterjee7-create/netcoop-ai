"""`netcoop fit`: fit the correlation model on training seeds, report calibration on holdout.

1. Run the full multi-agent pipeline on every generated run of the split (parallel) and
   extract candidates. A candidate is labelled true when its fault type maps to the run's
   ground-truth root cause and its root is one of the ground-truth locations; the labels come
   from the generator's own parameters, never from inspecting outputs.
2. Fit status likelihood ratios with shrinkage, then Platt scaling (training seeds).
3. Grid-search the accept / margin / no-fault thresholds: the most permissive ones whose
   decisions reach `decision.target_precision` on the training seeds.
4. Write config/correlation.yaml (generated, with rationale and source).
5. Score the held-out seeds: Brier score, ECE, reliability table, decision outcomes
   -> docs/CALIBRATION.md.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

import yaml

from netcoop.calibration import seed_split
from netcoop.catalogue import get_catalogue
from netcoop.config import CONFIG_DIR, get_value, load_config
from netcoop.correlation.features import Candidate, Context
from netcoop.correlation.model import Model, decide, fit_platt, fit_tables, qbin, sbin
from netcoop.generation import DEFAULT_OUT, META_FILE
from netcoop.protocol.vocabulary import get_vocabulary

MODEL_PATH = CONFIG_DIR / "correlation.yaml"
REPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "CALIBRATION.md"
RECORDS_DIR = Path(__file__).resolve().parents[2] / "runs" / "fit"


# ----------------------------------------------------------------------------- data collection
def truth_locations(gt: dict[str, Any]) -> set[str]:
    locs = set(gt.get("affected_entities") or [])
    for k in ("target_entity", "service"):
        if gt.get(k):
            locs.add(str(gt[k]))
    return locs


def collect(run: str) -> dict[str, Any]:
    """Worker: run the pipeline on one generated run and return its labelled candidates."""
    from netcoop.agents.scopes import Topo
    from netcoop.correlation.features import explains, extract
    from netcoop.orchestrator.orchestrator import Orchestrator
    from netcoop.orchestrator.stages import ProvisionalCorrelator
    from netcoop.protocol.common import MessageType

    path = Path(run)
    gt = json.loads((path / META_FILE).read_text(encoding="utf-8"))["ground_truth"]
    res = Orchestrator(correlator=ProvisionalCorrelator()).run(path)
    cands, ctx = extract(res.board)
    topo_msgs = res.board.query(type=MessageType.TOPOLOGY)
    topo = Topo(topo_msgs[-1].payload if topo_msgs else None)
    cat = get_catalogue()
    vocab = get_vocabulary()
    locs = truth_locations(gt)
    pairs = [
        [a.key, b.key] for a in cands for b in cands if a is not b and explains(a, b, cat, topo)
    ]
    return {
        "run": path.name,
        "family": gt["scenario"],
        "root_cause": gt["root_cause"],
        "noise": gt["noise"],
        "missing_rate": gt["missing_rate"],
        "intensity": gt["intensity"],
        "candidates": [
            {
                **c.to_record(),
                "key": c.key,
                "root_type": c.root_type,
                "true": vocab.hypothesis_types[c.hypothesis_type].family == gt["root_cause"]
                and c.root in locs,
            }
            for c in cands
        ],
        "ctx": {
            "mean_quality": ctx.mean_quality,
            "n_significant": ctx.n_significant,
            "unassessable": ctx.unassessable,
            "observed_metrics": sorted(ctx.observed_metrics),
            "assessed_metrics": sorted(ctx.assessed_metrics),
        },
        "explains": pairs,
    }


def split_runs(root: Path, seeds: set[int], stride: int) -> list[Path]:
    runs = []
    for fam in sorted(p for p in root.iterdir() if p.is_dir()):
        for d in sorted(fam.iterdir()):
            meta = d / META_FILE
            if (
                meta.is_file()
                and json.loads(meta.read_text(encoding="utf-8"))["ground_truth"]["seed"] in seeds
            ):
                runs.append(d)
    return runs[::stride]


def collect_all(runs: list[Path], workers: int) -> list[dict[str, Any]]:
    with cf.ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(collect, [str(r) for r in runs], chunksize=4))


# ----------------------------------------------------------------------------- decisions on records
def _cands(rec: dict[str, Any]) -> list[Candidate]:
    return [
        Candidate(
            c["type"],
            c["root"],
            c["root_type"],
            [c["key"]],
            [],
            (),
            tuple(c["statuses"]),
            (),
            c["analytic"],
            (),
            c["quality"],
        )
        for c in rec["candidates"]
    ]


def _ctx(rec: dict[str, Any]) -> Context:
    c = rec["ctx"]
    return Context(
        set(c["observed_metrics"]),
        set(c["assessed_metrics"]),
        c["n_significant"],
        c["mean_quality"],
        list(c["unassessable"]),
    )


def run_decision(rec: dict[str, Any], model: Model) -> tuple[str, str | None, float]:
    """(decision, winner key, confidence) for a collected run."""
    pairs = {tuple(p) for p in rec["explains"]}
    out = decide(
        _cands(rec), _ctx(rec), model, get_catalogue(), lambda a, b: (a.key, b.key) in pairs
    )
    return out.decision, out.winner.candidate.key if out.winner else None, out.confidence


def is_correct(rec: dict[str, Any], decision: str, winner: str | None) -> bool | None:
    """True/False for a claim, None for an abstention."""
    if decision == "insufficient_evidence":
        return None
    if decision == "no_fault_detected":
        return bool(rec["root_cause"] == "normal")
    truth = {c["key"] for c in rec["candidates"] if c["true"]}
    return bool(winner in truth)


# ----------------------------------------------------------------------------- fitting
def fit(train: list[dict[str, Any]]) -> tuple[Model, dict[str, Any]]:
    cat = get_catalogue()
    mcfg = load_config("correlation_method")
    alpha = float(get_value(mcfg, "estimation.laplace_alpha"))
    k = float(get_value(mcfg, "estimation.shrinkage_strength"))
    nq = int(get_value(mcfg, "estimation.quality_bins"))
    edges = list(get_value(mcfg, "estimation.significant_clue_bins"))
    target = float(get_value(mcfg, "decision.target_precision"))
    margins = list(get_value(mcfg, "decision.margin_grid"))
    min_accept = float(get_value(mcfg, "decision.min_accept"))
    l2 = float(get_value(mcfg, "estimation.platt_l2"))

    cands = [c for r in train for c in r["candidates"]]
    qcut = _quantiles(sorted(c["quality"] for c in cands), nq)
    model = Model(fit_tables(cands, cat, alpha, k, qcut), qcut)
    model.platt = fit_platt([model.score(c) for c in cands], [bool(c["true"]) for c in cands], l2)

    # accept / margin: maximise correct diagnoses s.t. precision >= target
    best = (-1.0, 2.0, 1.0, 0.0)  # (coverage, accept, margin, precision); accept 2.0 = never claim
    grid = [round(min_accept + i / 100, 2) for i in range(int((1 - min_accept) * 100))]
    fault_runs = sum(1 for r in train if r["root_cause"] != "normal")
    for acc in grid:
        for mg in margins:
            model.accept, model.margin, model.normal_accept = (
                acc,
                mg,
                2.0,
            )  # no-fault disabled while searching
            claims = [is_correct(r, *run_decision(r, model)[:2]) for r in train]
            made = [c for c in claims if c is not None]
            if not made:
                continue
            prec = sum(made) / len(made)
            cov = sum(made) / max(1, fault_runs)
            # most correct diagnoses at the target precision; ties -> the stricter threshold
            if prec >= target and (cov > best[0] or (cov == best[0] and acc > best[1])):
                best = (cov, acc, mg, prec)
    model.accept, model.margin = best[1], best[2]

    # no-fault table on runs left undiagnosed by the chosen thresholds
    undiagnosed = [
        r
        for r in train
        if run_decision(r, _with(model, normal_accept=2.0))[0] != "diagnosed"
        and not r["ctx"]["unassessable"]
    ]
    nqcut = _quantiles(sorted(r["ctx"]["mean_quality"] for r in undiagnosed), nq)
    g = (sum(r["root_cause"] == "normal" for r in undiagnosed) + alpha) / (
        len(undiagnosed) + 2 * alpha
    )
    cells: dict[str, list[bool]] = defaultdict(list)
    for r in undiagnosed:
        cells[
            f"{qbin(r['ctx']['mean_quality'], nqcut)},{sbin(r['ctx']['n_significant'], edges)}"
        ].append(r["root_cause"] == "normal")
    table = {key: (sum(v) + k * g) / (len(v) + k) for key, v in sorted(cells.items())}
    model.normal_quality_cutoffs, model.significant_edges, model.normal_table = nqcut, edges, table
    model.normal_accept = 2.0
    for t in sorted(set(table.values())):
        sel = [r for r in undiagnosed if model.p_normal(_ctx(r)) >= t]
        if sel and sum(r["root_cause"] == "normal" for r in sel) / len(sel) >= target:
            model.normal_accept = t
            break
    summary = {
        "train_runs": len(train),
        "train_candidates": len(cands),
        "train_true_candidates": sum(c["true"] for c in cands),
        "train_diagnosis_precision": best[3],
        "train_fault_coverage": best[0],
    }
    return model, summary


def _with(model: Model, **kw: Any) -> Model:
    m = Model.from_dict(model.to_dict())
    for k, v in kw.items():
        setattr(m, k, v)
    return m


def _quantiles(xs: list[float], n: int) -> list[float]:
    if not xs:
        return []
    return [xs[min(len(xs) - 1, int(len(xs) * i / n))] for i in range(1, n)]


# ----------------------------------------------------------------------------- persistence
def save(
    model: Model, summary: dict[str, Any], train_seeds: list[int], path: Path = MODEL_PATH
) -> None:
    when = datetime.now(UTC).strftime("%Y-%m-%d")
    src = (
        f"fitted by `netcoop fit` on {summary['train_runs']} generated runs (all families), "
        "training seeds "
        f"{train_seeds}, {when}"
    )
    doc = {
        "description": "GENERATED by `netcoop fit` - do not edit by hand. Correlation model "
        "(docs/SCORING.md "
        "section 4). Re-fit after changing agents, detection, catalogue or generator.",
        "model": {
            "value": model.to_dict(),
            "unit": "log-likelihood ratios; Platt (a, b); calibrated thresholds",
            "rationale": "Naive-Bayes evidence model with shrinkage, Platt-calibrated, decision "
            "thresholds "
            "chosen for the target precision on training seeds.",
            "source": src,
        },
        "training_summary": {
            "value": summary,
            "unit": "counts and fractions",
            "rationale": "Fit diagnostics, for traceability.",
            "source": src,
        },
    }
    path.write_text(yaml.safe_dump(doc, sort_keys=True, width=110), encoding="utf-8")


def load_model(path: Path = MODEL_PATH) -> Model | None:
    if not path.is_file():
        return None
    return Model.from_dict(load_config(path.stem, path.parent)["model"]["value"])


# ----------------------------------------------------------------------------- evaluation
def calibration_metrics(pairs: list[tuple[float, bool]], bins: int) -> dict[str, Any]:
    n = len(pairs)
    brier = sum((p - y) ** 2 for p, y in pairs) / n if n else math.nan
    table = []
    ece = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(p, y) for p, y in pairs if lo <= p < hi or (b == bins - 1 and p == 1.0)]
        if sel:
            conf, acc = fmean(p for p, _ in sel), fmean(float(y) for _, y in sel)
            ece += len(sel) / n * abs(conf - acc)
            table.append((lo, hi, len(sel), conf, acc))
    base = sum(y for _, y in pairs) / n if n else math.nan
    return {"n": n, "brier": brier, "brier_baseline": base * (1 - base), "ece": ece, "table": table}


def evaluate(records: list[dict[str, Any]], model: Model) -> dict[str, Any]:
    bins = int(get_value(load_config("correlation_method"), "calibration.ece_bins"))
    pairs = [(model.confidence(c), bool(c["true"])) for r in records for c in r["candidates"]]
    outcomes: dict[str, Counter[str]] = defaultdict(Counter)
    by_missing: dict[float, Counter[str]] = defaultdict(Counter)
    by_noise: dict[float, Counter[str]] = defaultdict(Counter)
    for r in records:
        d, w, _ = run_decision(r, model)
        ok = is_correct(r, d, w)
        label = "abstain" if ok is None else ("correct" if ok else "wrong")
        detail = f"{label}:{d}"
        outcomes[r["family"]][detail] += 1
        by_missing[r["missing_rate"]][label] += 1
        by_noise[r["noise"]][label] += 1
    return {
        "calibration": calibration_metrics(pairs, bins),
        "outcomes": outcomes,
        "by_missing": by_missing,
        "by_noise": by_noise,
    }


def render_report(
    train_summary: dict[str, Any],
    model: Model,
    train_eval: dict[str, Any],
    hold_eval: dict[str, Any],
    seeds: tuple[list[int], list[int]],
) -> str:
    def cal_block(name: str, ev: dict[str, Any]) -> list[str]:
        c = ev["calibration"]
        lines = [
            f"### {name}",
            "",
            f"Candidates: {c['n']}. Brier score **{c['brier']:.4f}** (no-skill baseline "
            f"{c['brier_baseline']:.4f}), "
            f"ECE **{c['ece']:.4f}**.",
            "",
            "| confidence bin | candidates | mean confidence | observed accuracy |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {lo:.1f}–{hi:.1f} | {n} | {cf:.3f} | {acc:.3f} |"
            for lo, hi, n, cf, acc in c["table"]
        ]
        return [*lines, ""]

    def outcome_block(name: str, ev: dict[str, Any]) -> list[str]:
        lines = [
            f"### {name}: decisions per scenario family",
            "",
            "| family | runs | correct | wrong | abstained | breakdown |",
            "|---|---|---|---|---|---|",
        ]
        tot: Counter[str] = Counter()
        for fam, cnt in sorted(ev["outcomes"].items()):
            agg = Counter(k.split(":")[0] for k in cnt.elements())
            tot.update(agg)
            n = sum(cnt.values())
            lines.append(
                f"| {fam} | {n} | {agg['correct']} ({agg['correct'] / n:.0%}) | {agg['wrong']} "
                f"({agg['wrong'] / n:.0%}) | {agg['abstain']} ({agg['abstain'] / n:.0%}) | "
                + ", ".join(f"{k} {v}" for k, v in sorted(cnt.items()))
                + " |"
            )
        n = sum(tot.values())
        claims = tot["correct"] + tot["wrong"]
        lines += [
            f"| **all** | {n} | {tot['correct']} ({tot['correct'] / n:.0%}) | {tot['wrong']} "
            f"({tot['wrong'] / n:.0%}) "
            f"| {tot['abstain']} ({tot['abstain'] / n:.0%}) | precision of claims "
            f"**{tot['correct'] / max(1, claims):.1%}** |",
            "",
        ]
        for key, title in (("by_missing", "missing-data rate"), ("by_noise", "noise level")):
            lines += [
                f"By {title}:",
                "",
                f"| {title} | correct | wrong | abstained | precision of claims |",
                "|---|---|---|---|---|",
            ]
            for lvl, cnt in sorted(ev[key].items()):
                n = sum(cnt.values())
                cl = cnt["correct"] + cnt["wrong"]
                lines.append(
                    f"| {lvl} | {cnt['correct'] / n:.0%} | {cnt['wrong'] / n:.0%} | "
                    f"{cnt['abstain'] / n:.0%} | "
                    f"{cnt['correct'] / max(1, cl):.1%} |"
                )
            lines.append("")
        return lines

    lines = [
        "# Correlation model: calibration and decisions",
        "",
        "Generated by `netcoop fit`. Fitted on training seeds "
        f"{seeds[0]}, evaluated on held-out seeds {seeds[1]} (see D-025 on held-out hygiene).",
        "",
        "## Fitted operating point",
        "",
        f"- Training: {train_summary['train_runs']} runs, {train_summary['train_candidates']} "
        "candidates "
        f"({train_summary['train_true_candidates']} true).",
        f"- Accept threshold **{model.accept:.2f}**, margin **{model.margin:.2f}**, "
        f"no-fault threshold **{model.normal_accept:.2f}** (training precision of diagnoses "
        f"{train_summary['train_diagnosis_precision']:.1%}, coverage "
        f"{train_summary['train_fault_coverage']:.1%}).",
        f"- Platt scaling a = {model.platt[0]:.3f}, b = {model.platt[1]:.3f}.",
        "",
        "## Candidate calibration",
        "",
        *cal_block("Held-out seeds", hold_eval),
        *cal_block("Training seeds (for comparison)", train_eval),
        "## Decisions",
        "",
        "'Correct' = right fault type at a true location, or `no_fault_detected` on a normal run. "
        "'Wrong' = "
        "any other claim. 'Abstained' = `insufficient_evidence` (includes near ties that the "
        "Phase 6 "
        "courtroom may resolve).",
        "",
        *outcome_block("Held-out seeds", hold_eval),
        *outcome_block("Training seeds", train_eval),
    ]
    return "\n".join(lines)


def run_fit(
    root: Path = DEFAULT_OUT, report: Path = REPORT_PATH, stride: int | None = None
) -> dict[str, Any]:
    mcfg = load_config("correlation_method")
    workers = int(get_value(mcfg, "fitting.workers"))
    stride = stride or int(get_value(mcfg, "fitting.runs_stride"))
    train_seeds, hold_seeds = seed_split()
    train_runs = split_runs(root, set(train_seeds), stride)
    hold_runs = split_runs(root, set(hold_seeds), stride)
    if not train_runs:
        raise ValueError(f"no generated runs under {root}; run `netcoop generate`")
    train = collect_all(train_runs, workers)
    model, summary = fit(train)
    save(model, summary, train_seeds)
    hold = collect_all(hold_runs, workers) if hold_runs else []
    RECORDS_DIR.mkdir(
        parents=True, exist_ok=True
    )  # kept for analysis (e.g. near ties), not committed
    for name, recs in (("train", train), ("holdout", hold)):
        (RECORDS_DIR / f"{name}.json").write_text(json.dumps(recs), encoding="utf-8")
    train_eval = evaluate(train, model)
    hold_eval = evaluate(hold, model) if hold else train_eval
    report.write_text(
        render_report(summary, model, train_eval, hold_eval, (train_seeds, hold_seeds)) + "\n",
        encoding="utf-8",
    )
    return {"summary": summary, "model": model, "holdout": hold_eval}
