"""Evaluation metrics over harness records (definitions in docs/EVALUATION.md).

Labels are scenario families of the *ground-truth root cause* (for interop runs, the
underlying network state). A prediction is the family of the claimed fault, ``normal`` for
no_fault_detected, or ``abstain``. A claim is correct when the family matches and, for
faults, the claimed root is one of the true locations.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import fmean
from typing import Any

from netcoop.correlation.fit import calibration_metrics
from netcoop.protocol.vocabulary import get_vocabulary

ABSTAIN, NORMAL = "abstain", "normal"


def predicted(rec: dict[str, Any]) -> str:
    if rec["status"] == "insufficient_evidence":
        return ABSTAIN
    if rec["status"] == "no_fault_detected":
        return NORMAL
    fam = get_vocabulary().hypothesis_types[rec["claimed_type"]].family
    return fam or rec["claimed_type"]


def correct(rec: dict[str, Any]) -> bool:
    p = predicted(rec)
    if p != rec["root_cause"]:
        return False
    return p == NORMAL or rec["claimed_root"] in rec["locations"]


def _guess_correct(rec: dict[str, Any]) -> bool:
    """Would the best available guess (top candidate, else 'normal') have been right?"""
    vocab = get_vocabulary()
    if not rec["ranking"]:
        return bool(rec["root_cause"] == NORMAL)
    t, root, _ = rec["ranking"][0]
    return vocab.hypothesis_types[t].family == rec["root_cause"] and root in rec["locations"]


def summary(recs: list[dict[str, Any]], bins: int) -> dict[str, Any]:
    n = len(recs)
    if n == 0:
        return {"n": 0}
    preds = [predicted(r) for r in recs]
    ok = [correct(r) for r in recs]
    claims = [i for i, p in enumerate(preds) if p != ABSTAIN]
    labels = sorted({r["root_cause"] for r in recs})
    f1s = {}
    for lab in labels:
        tp = sum(1 for i, r in enumerate(recs) if r["root_cause"] == lab and ok[i])
        n_pred = sum(1 for i in claims if preds[i] == lab)
        n_true = sum(1 for r in recs if r["root_cause"] == lab)
        prec = tp / n_pred if n_pred else 0.0
        rec_ = tp / n_true if n_true else 0.0
        f1s[lab] = {
            "precision": prec,
            "recall": rec_,
            "f1": 2 * prec * rec_ / (prec + rec_) if prec + rec_ else 0.0,
            "support": n_true,
        }
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for r, p in zip(recs, preds, strict=True):
        confusion[r["root_cause"]][p] += 1

    loc_p, loc_r, wrong_loc = [], [], 0
    for r, p in zip(recs, preds, strict=True):
        if p in (ABSTAIN, NORMAL) or p != r["root_cause"]:
            continue
        truth = set(r["truth_affected"]) | set(r["locations"])
        aff = set(r["affected"])
        if r["claimed_root"] not in r["locations"]:
            wrong_loc += 1
        if aff:
            loc_p.append(len(aff & truth) / len(aff))
        if r["truth_affected"]:
            loc_r.append(len(aff & set(r["truth_affected"])) / len(r["truth_affected"]))

    abst = [r for r, p in zip(recs, preds, strict=True) if p == ABSTAIN]
    justified = sum(1 for r in abst if not _guess_correct(r))
    guess_wrong = sum(1 for r in recs if not _guess_correct(r))
    caught = sum(
        1 for r, p in zip(recs, preds, strict=True) if p == ABSTAIN and not _guess_correct(r)
    )

    vocab = get_vocabulary()
    pairs = []
    for r in recs:
        for t, root, conf in r["ranking"]:
            pairs.append(
                (
                    float(conf),
                    vocab.hypothesis_types[t].family == r["root_cause"] and root in r["locations"],
                )
            )
    return {
        "n": n,
        "accuracy": sum(ok) / n,
        "claims": len(claims),
        "claim_precision": sum(ok[i] for i in claims) / len(claims) if claims else 0.0,
        "wrong": len(claims) - sum(ok[i] for i in claims),
        "abstain_rate": len(abst) / n,
        "macro_f1": fmean(v["f1"] for v in f1s.values()),
        "per_label": f1s,
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "localisation_precision": fmean(loc_p) if loc_p else None,
        "localisation_recall": fmean(loc_r) if loc_r else None,
        "right_type_wrong_location": wrong_loc,
        "root_localisation": (1 - wrong_loc / n_type_right)
        if (
            n_type_right := sum(
                1
                for r, p in zip(recs, preds, strict=True)
                if p not in (ABSTAIN, NORMAL) and p == r["root_cause"]
            )
        )
        else None,
        "abstention_precision": justified / len(abst) if abst else None,
        "abstention_recall": caught / guess_wrong if guess_wrong else None,
        "calibration": calibration_metrics(pairs, bins) if pairs else None,
        "courtroom_invoked": sum(r["courtroom"] for r in recs),
    }


def slices(recs: list[dict[str, Any]], key: str) -> dict[Any, dict[str, float]]:
    groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for r in recs:
        groups[r[key] if key != "mutations" else len(r[key])].append(r)
    out = {}
    for k, rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
        ok = [correct(r) for r in rs]
        claims = [o for r, o in zip(rs, ok, strict=True) if predicted(r) != ABSTAIN]
        out[k] = {
            "n": len(rs),
            "accuracy": sum(ok) / len(rs),
            "precision": sum(claims) / len(claims) if claims else 0.0,
            "abstain": sum(predicted(r) == ABSTAIN for r in rs) / len(rs),
        }
    return out
