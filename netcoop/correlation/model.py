"""Naive-Bayes evidence model, Platt calibration and the decision policy (SCORING.md section 4).

score(candidate) = prior_logit[type]
                 + sum over signature elements e of LLR[type][e][status_e]
                 + LLR_analytic[status] + LLR_quality[bin]
confidence = sigmoid(a * score + b)                         (Platt scaling)

LLRs are log(P(status | candidate true) / P(status | candidate false)) estimated from labelled
training candidates with Laplace smoothing and empirical-Bayes shrinkage toward the pooled
rate of elements with the same (role, expect). Everything is fitted by `netcoop fit` and
stored in config/correlation.yaml.
"""

from __future__ import annotations

import bisect
import math
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from netcoop.catalogue import Catalogue
from netcoop.correlation.features import NONE, Candidate, Context

STATUSES = ("satisfied", "violated", "unknown")
ANALYTIC = ("support", "contradict", "none")


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x)) if x >= 0 else math.exp(x) / (1.0 + math.exp(x))


def qbin(value: float, cutoffs: list[float]) -> int:
    return bisect.bisect_right(cutoffs, value)


def sbin(n: int, edges: list[int]) -> int:
    return max(0, bisect.bisect_right(edges, n) - 1)


# ----------------------------------------------------------------------------- estimation
def fit_tables(
    cands: list[dict[str, Any]], cat: Catalogue, alpha: float, k: float, qcut: list[float]
) -> dict[str, Any]:
    """Estimate prior log-odds and status log-likelihood ratios from labelled candidates."""
    pooled: dict[bool, dict[tuple[str, str], dict[str, float]]] = {
        True: defaultdict(lambda: defaultdict(float)),
        False: defaultdict(lambda: defaultdict(float)),
    }
    elem: dict[tuple[str, int, bool], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    n_type: dict[tuple[str, bool], int] = defaultdict(int)
    analytic: dict[bool, dict[str, float]] = {True: defaultdict(float), False: defaultdict(float)}
    quality: dict[bool, dict[int, float]] = {True: defaultdict(float), False: defaultdict(float)}
    for c in cands:
        y, h = bool(c["true"]), cat.hypotheses[c["type"]]
        n_type[(c["type"], y)] += 1
        for i, (e, s) in enumerate(zip(h.signature, c["statuses"], strict=True)):
            pooled[y][(e.role, e.expect)][s] += 1
            elem[(c["type"], i, y)][s] += 1
        analytic[y][c["analytic"]] += 1
        quality[y][qbin(c["quality"], qcut)] += 1

    def rate(counts: dict[Any, float], keys: tuple[Any, ...]) -> dict[Any, float]:
        total = sum(counts.get(s, 0.0) for s in keys)
        return {s: (counts.get(s, 0.0) + alpha) / (total + alpha * len(keys)) for s in keys}

    def llr(t: dict[Any, float], f: dict[Any, float]) -> dict[str, float]:
        return {str(s): math.log(t[s] / f[s]) for s in t}

    n_true = sum(v for (_, y), v in n_type.items() if y)
    n_all = sum(n_type.values())
    g = (n_true + alpha) / (n_all + 2 * alpha)
    types: dict[str, Any] = {}
    for hid, h in cat.hypotheses.items():
        nt, nf = n_type[(hid, True)], n_type[(hid, False)]
        r = (nt + k * g) / (nt + nf + k)
        elements = []
        for i, e in enumerate(h.signature):
            shrunk = {}
            for y in (True, False):
                pool = rate(pooled[y][(e.role, e.expect)], STATUSES)
                counts = elem[(hid, i, y)]
                n = sum(counts.values())
                shrunk[y] = {s: (counts.get(s, 0.0) + k * pool[s]) / (n + k) for s in STATUSES}
            elements.append(llr(shrunk[True], shrunk[False]))
        types[hid] = {
            "prior_logit": math.log(r / (1 - r)),
            "elements": elements,
            "n_true": nt,
            "n_false": nf,
        }
    n_bins = len(qcut) + 1
    return {
        "types": types,
        "analytic": llr(rate(analytic[True], ANALYTIC), rate(analytic[False], ANALYTIC)),
        "quality": llr(
            rate(quality[True], tuple(range(n_bins))), rate(quality[False], tuple(range(n_bins)))
        ),
    }


def fit_platt(
    scores: list[float], labels: list[bool], l2: float, iters: int = 100
) -> tuple[float, float]:
    """1-D logistic regression p = sigmoid(a*s + b) by Newton's method with a small ridge."""
    a, b = 1.0, 0.0
    for _ in range(iters):
        ga = gb = haa = hab = hbb = 0.0
        for s, y in zip(scores, labels, strict=True):
            p = sigmoid(a * s + b)
            r = p - float(y)
            w = p * (1 - p)
            ga += r * s
            gb += r
            haa += w * s * s
            hab += w * s
            hbb += w
        ga += l2 * a
        gb += l2 * b
        haa += l2
        hbb += l2
        det = haa * hbb - hab * hab
        if det <= 0:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) + abs(db) < 1e-10:
            break
    return a, b


# ----------------------------------------------------------------------------- scoring
@dataclass
class Model:
    tables: dict[str, Any]
    quality_cutoffs: list[float]
    platt: tuple[float, float] = (1.0, 0.0)
    accept: float = 1.0
    margin: float = 1.0
    normal_accept: float = 1.0
    normal_quality_cutoffs: list[float] = field(default_factory=list)
    significant_edges: list[int] = field(default_factory=lambda: [0])
    normal_table: dict[str, float] = field(default_factory=dict)

    def score(self, c: Candidate | dict[str, Any]) -> float:
        rec = c.to_record() if isinstance(c, Candidate) else c
        t = self.tables["types"][rec["type"]]
        s = t["prior_logit"] + sum(
            el[st] for el, st in zip(t["elements"], rec["statuses"], strict=True)
        )
        s += self.tables["analytic"][rec["analytic"]]
        s += self.tables["quality"][str(qbin(rec["quality"], self.quality_cutoffs))]
        return float(s)

    def logit(self, c: Candidate | dict[str, Any]) -> float:
        """Calibrated log-odds a*score+b (does not saturate, unlike the probability)."""
        a, b = self.platt
        return a * self.score(c) + b

    def confidence(self, c: Candidate | dict[str, Any]) -> float:
        return sigmoid(self.logit(c))

    def p_normal(self, ctx: Context) -> float:
        q = qbin(ctx.mean_quality, self.normal_quality_cutoffs)
        key = f"{q},{sbin(ctx.n_significant, self.significant_edges)}"
        return self.normal_table.get(key, 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tables": self.tables,
            "quality_cutoffs": self.quality_cutoffs,
            "platt": list(self.platt),
            "accept": self.accept,
            "margin": self.margin,
            "normal_accept": self.normal_accept,
            "normal_quality_cutoffs": self.normal_quality_cutoffs,
            "significant_edges": self.significant_edges,
            "normal_table": self.normal_table,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Model:
        return cls(
            d["tables"],
            d["quality_cutoffs"],
            tuple(d["platt"]),
            d["accept"],
            d["margin"],
            d["normal_accept"],
            d["normal_quality_cutoffs"],
            d["significant_edges"],
            d["normal_table"],
        )


# ----------------------------------------------------------------------------- decision
@dataclass
class Ranked:
    candidate: Candidate
    score: float
    confidence: float
    logit: float
    merged_into: str | None = None
    absorbed: list[str] = field(default_factory=list)


@dataclass
class Outcome:
    decision: str  # diagnosed | insufficient_evidence | no_fault_detected
    confidence: float
    ranking: list[Ranked]
    winner: Ranked | None
    rationale: list[str]
    missing_evidence: list[str]
    near_tie: bool = False


ExplainsFn = Callable[[Candidate, Candidate], bool]


def decide(
    cands: list[Candidate], ctx: Context, model: Model, cat: Catalogue, explains_fn: ExplainsFn
) -> Outcome:
    # rank on calibrated log-odds: probabilities saturate at 1.0 and would tie
    ranked = sorted(
        (Ranked(c, model.score(c), model.confidence(c), model.logit(c)) for c in cands),
        key=lambda r: (-r.logit, r.candidate.key),
    )
    # causal precedence: an effect explained by an at-least-as-confident cause stops competing
    for i, eff in enumerate(ranked):
        for cause in ranked[:i]:
            if cause.merged_into is None and explains_fn(cause.candidate, eff.candidate):
                eff.merged_into = cause.candidate.key
                cause.absorbed.append(eff.candidate.key)
                break
    live = [r for r in ranked if r.merged_into is None]
    rationale: list[str] = []
    missing = _missing(live[:3], cat, ctx)
    top = live[0] if live else None
    gap = top.logit - live[1].logit if top is not None and len(live) > 1 else math.inf
    if top is not None and top.confidence >= model.accept:
        if gap >= model.margin:
            rationale += [
                "top_candidate_accepted",
                f"log-odds margin {gap:.2f} >= {model.margin:.2f}",
            ]
            return Outcome("diagnosed", top.confidence, ranked, top, rationale, [])
        rationale += ["near_tie", f"log-odds margin {gap:.2f} < {model.margin:.2f}"]
        return Outcome(
            "insufficient_evidence", top.confidence, ranked, None, rationale, missing, near_tie=True
        )
    if top is not None:
        rationale.append(
            f"best candidate confidence {top.confidence:.2f} < accept {model.accept:.2f}"
        )
    if ctx.blocking:
        # Part of the input or of the analysis was lost (unusable file, failed agent): what was
        # not seen cannot be declared healthy (found by the Phase 8 robustness evaluation).
        rationale.append("cannot_rule_out: " + "; ".join(dict.fromkeys(ctx.blocking)))
        missing += [f"usable data / analysis instead of {b}" for b in dict.fromkeys(ctx.blocking)]
        return Outcome(
            "insufficient_evidence",
            top.confidence if top else 0.0,
            ranked,
            None,
            rationale,
            missing,
        )
    if ctx.unassessable:
        rationale.append("cannot_rule_out:" + ",".join(ctx.unassessable))
        missing += [
            f"no evidence to assess {h} (required metrics not observed or not analysed)"
            for h in ctx.unassessable
        ]
        return Outcome(
            "insufficient_evidence",
            top.confidence if top else 0.0,
            ranked,
            None,
            rationale,
            missing,
        )
    pn = model.p_normal(ctx)
    if pn >= model.normal_accept:
        rationale.append(f"P(normal | quality, anomalies) {pn:.2f} >= {model.normal_accept:.2f}")
        return Outcome("no_fault_detected", pn, ranked, None, rationale, [])
    rationale.append(f"P(normal | quality, anomalies) {pn:.2f} < {model.normal_accept:.2f}")
    return Outcome(
        "insufficient_evidence",
        top.confidence if top else 0.0,
        ranked,
        None,
        rationale,
        missing or ["more complete or less noisy telemetry for the affected period"],
    )


def _missing(top: list[Ranked], cat: Catalogue, ctx: Context) -> list[str]:
    out: list[str] = []
    for r in top:
        h = cat.hypotheses[r.candidate.hypothesis_type]
        for e, s in zip(h.signature, r.candidate.statuses, strict=True):
            if s == "unknown":
                why = (
                    "not observed"
                    if e.metric not in ctx.observed_metrics
                    else "not analysed by any agent"
                    if e.metric not in ctx.assessed_metrics
                    else "no data in scope"
                )
                out.append(
                    f"{e.metric} ({e.direction}) at {e.scope} of {r.candidate.root} for "
                    f"{r.candidate.hypothesis_type}: {why}"
                )
    return list(dict.fromkeys(out))


__all__ = ["NONE", "ExplainsFn", "Model", "Outcome", "Ranked", "decide", "fit_platt", "fit_tables"]
