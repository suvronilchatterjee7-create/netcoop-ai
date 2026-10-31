"""Recommendation and Reporting agent: final VERDICT + board -> unified report (docs/REPORTING.md).

* **Evidence** comes from the correlator's recomputed signature of the reported candidate
  (or the best contenders when no cause is claimed): satisfied elements, required first,
  strongest deviation first, each traced to its clue, agent, reference and observations.
* **Interpretations** are generated from each clue's evidence model (statistic, value,
  reference and its basis, normalised deviation, persistence, data quality), never canned.
* **Actions** are the catalogue's parametrised actions filled with the real entities. When no
  cause is claimed, they become data-collection steps plus conditional actions per contender.
* **Limitations** gather translator and agent errors, failed or inactive agents,
  non-convergence, unassessable fault types, low-quality evidence and courtroom deferrals.
* **Extensions** (x_netcoop): confidence category, provenance, itemised log-odds, scored
  alternatives, data-quality summary, courtroom summary, dry-run remediation, run manifest.
"""

from __future__ import annotations

from collections import Counter
from statistics import fmean
from typing import Any

from netcoop.board.board import Board
from netcoop.catalogue import HypothesisSpec, get_catalogue
from netcoop.config import get_value, load_config
from netcoop.correlation.features import Candidate, Context, extract, index_board
from netcoop.correlation.fit import load_model
from netcoop.correlation.model import qbin
from netcoop.orchestrator.stages import RunInfo, base_limitations, courtroom_summary
from netcoop.protocol.capability import AgentRole, CapabilityCard
from netcoop.protocol.common import (
    PROTOCOL_VERSION,
    ComparisonBasis,
    Decision,
    EntityRole,
    MessageType,
    Statistic,
)
from netcoop.protocol.messages import Envelope
from netcoop.protocol.payloads import CluePayload, VerdictPayload
from netcoop.protocol.report import (
    DataQualitySummary,
    EvidenceItem,
    EvidenceProvenance,
    Report,
    ReportExtensions,
    ReportStatus,
    ScoredAlternative,
    ScoreTerm,
    SimulatedAction,
)

T = MessageType
NOTHING_ASSERTED = "none"  # confidence category when no root cause (and no 'no fault') is asserted
_STATUS = {
    Decision.DIAGNOSED: ReportStatus.DIAGNOSED,
    Decision.INSUFFICIENT_EVIDENCE: ReportStatus.INSUFFICIENT_EVIDENCE,
    Decision.NO_FAULT_DETECTED: ReportStatus.NO_FAULT_DETECTED,
}
_DEV_UNITS = {
    "robust_z": "robust standard deviations",
    "median_shift_z": "standard errors of the shift",
    "relative_to_threshold": "x the threshold (relative excess)",
    "mann_kendall_z": "(Mann-Kendall z)",
    "fraction_abnormal": "",
}
_BASIS = {
    "calibrated_percentile_band": "normal-operation baseline",
    "cited_threshold": "cited threshold",
    "in_window_change": "series' own earlier level",
}


def key_of(hypothesis_type: str, root: str) -> str:
    return f"{hypothesis_type}@{root}"


def interpret(c: CluePayload, expect: str, hypothesis: str) -> str:
    """One sentence from a clue's evidence model."""
    where = c.entity.entity_id + (f" (probed from {c.observed_from})" if c.observed_from else "")
    ref = c.comparison.reference_value
    basis = _BASIS.get(c.comparison.method, c.comparison.basis.value)
    q = f"; data quality {c.data_quality:.2f} [{c.comparison.config_key}]"
    if c.statistic is Statistic.SLOPE:
        return (
            f"{c.metric} on {where} is rising by {float(c.value):.3g} {c.unit} "
            f"(Mann-Kendall z {c.deviation:.1f}){q}"
        )
    if c.statistic is Statistic.FRACTION:
        return (
            f"{c.metric} on {where} was in an abnormal state in {float(c.value):.0%} "
            f"of recent samples{q}"
        )
    ref_txt = f"{float(ref):.3g} {c.unit}" if isinstance(ref, int | float) else "reference"
    if expect == "normal" or not c.significant:
        return (
            f"{c.metric} on {where} stayed normal: recent median {float(c.value):.3g} {c.unit} vs "
            f"{basis} {ref_txt}, as {hypothesis} predicts{q}"
        )
    pers = (
        f", abnormal in {c.persistence:.0%} of recent samples" if c.persistence is not None else ""
    )
    return (
        f"{c.metric} on {where}: recent median {float(c.value):.3g} {c.unit} "
        f"is {c.direction.value} the "
        f"{basis} of {ref_txt} by {c.deviation:.3g} "
        f"{_DEV_UNITS.get(c.deviation_unit, c.deviation_unit)}"
        f"{pers}{q}"
    )


class Reporter:
    card = CapabilityCard(
        agent_id="reporter",
        version="0.1.0",
        role=AgentRole.REPORTER,
        description="Recommendation and Reporting agent: unified A7 report with traced evidence, "
        "generated "
        "interpretations, catalogue actions, aggregated limitations and a dry-run remediation.",
        protocol_versions=(PROTOCOL_VERSION,),
        consumes_types=(T.VERDICT, T.CLUE, T.HYPOTHESIS, T.ERROR),
        consumes_metrics=("*",),
        produces_types=(T.REPORT,),
    )

    def __init__(self) -> None:
        cfg = load_config("reporting")
        self.max_items = int(get_value(cfg, "evidence.max_items"))
        self.max_contenders = int(get_value(cfg, "evidence.max_contenders"))
        self.alt_min = float(get_value(cfg, "alternatives.min_confidence"))
        self.low_q = float(get_value(cfg, "quality.low_threshold"))
        self.no_fault_actions = list(get_value(cfg, "actions.no_fault"))
        self.if_prefix = str(get_value(cfg, "actions.insufficient_prefix"))
        self.collect_prefix = str(get_value(cfg, "actions.collect_prefix"))
        self.cat = get_catalogue()
        self.model = load_model()

    # ------------------------------------------------------------------ main
    def report(self, board: Board, verdict: Envelope, run: RunInfo) -> Report:
        v: VerdictPayload = verdict.payload
        cands, ctx = extract(board, self.cat)
        by_key = {c.key: c for c in cands}
        idx = index_board(board)
        clue_by_id = {m.msg_id: m for ms in idx.clues.values() for m in ms}
        winner = self._winner(v, by_key)
        focus = [winner] if winner else self._contenders(v, by_key)

        evidence, provenance, used = self._evidence(focus, clue_by_id)
        affected = self._affected(winner, focus, used)
        actions = self._actions(v, winner, focus, idx, ctx)
        remediation = self._simulate(winner, actions, used) if winner else ()
        alts, scored = self._alternatives(v, winner)
        sources = list(dict.fromkeys([*(m.sender for m in used), "correlator"]))
        if winner and winner.analytic_ids:
            sources += [m.sender for i in winner.analytic_ids if (m := board.get(i)) is not None]
        if v.method == "courtroom":
            sources += ["prosecutor", "defense", "judge"]
        return Report(
            incident_id=run.incident_id,
            status=_STATUS[v.decision],
            suspected_root_cause=self._cause(v, winner, focus),
            # confidence in what is asserted: the root cause, or 'no fault'; nothing asserted -> 0
            confidence=v.confidence if v.decision is not Decision.INSUFFICIENT_EVIDENCE else 0.0,
            affected_devices=tuple(affected),
            supporting_evidence=tuple(evidence),
            alternative_causes=tuple(alts),
            recommended_actions=tuple(actions),
            evidence_sources=tuple(dict.fromkeys(sources)),
            limitations=self._limitations(board, run, v, ctx, used),
            x_netcoop=ReportExtensions(
                confidence_category=(
                    v.confidence_category
                    if v.decision is not Decision.INSUFFICIENT_EVIDENCE
                    else NOTHING_ASSERTED
                ),
                evidence_provenance=tuple(provenance),
                alternatives_scored=tuple(scored),
                data_quality=self._quality(board, ctx, affected),
                courtroom=courtroom_summary(board, v),
                missing_evidence=v.missing_evidence,
                score_breakdown=tuple(self._breakdown(winner or (focus[0] if focus else None))),
                simulated_remediation=remediation,
                manifest=run.manifest,
            ),
        )

    # ------------------------------------------------------------------ selection
    def _winner(self, v: VerdictPayload, by_key: dict[str, Candidate]) -> Candidate | None:
        if v.decision is not Decision.DIAGNOSED or not v.hypothesis_type:
            return None
        root = next((e.entity.entity_id for e in v.entities if e.role is EntityRole.ROOT), None)
        return by_key.get(key_of(v.hypothesis_type, root)) if root else None

    def _contenders(self, v: VerdictPayload, by_key: dict[str, Candidate]) -> list[Candidate]:
        out = []
        for r in v.ranking:
            root = next((e.entity.entity_id for e in r.entities if e.role is EntityRole.ROOT), None)
            c = by_key.get(key_of(r.hypothesis_type, root)) if root else None
            if c is not None and c not in out:
                out.append(c)
        return out[: self.max_contenders]

    def _evidence(
        self, focus: list[Candidate], clue_by_id: dict[str, Envelope]
    ) -> tuple[list[EvidenceItem], list[EvidenceProvenance], list[Envelope]]:
        picks: list[
            tuple[int, float, Envelope, str, str]
        ] = []  # (rank, -deviation, clue, expect, hypothesis)
        for c in focus:
            h = self.cat.hypotheses[c.hypothesis_type]
            for i, (e, s) in enumerate(zip(h.signature, c.statuses, strict=True)):
                if s != "satisfied":
                    continue
                clues = [clue_by_id[x] for x in c.element_clues[i] if x in clue_by_id]
                clues.sort(
                    key=lambda m: (
                        -m.payload.deviation if e.expect == "deviates" else m.payload.deviation,
                        m.msg_id,
                    )
                )
                for n, m in enumerate(clues[: 1 if e.expect == "normal" else len(clues)]):
                    rank = (
                        0 if e.role == "required" else 1
                    ) + 2 * n  # one per element first, required first
                    picks.append((rank, -m.payload.deviation, m, e.expect, h.id))
        picks.sort(key=lambda p: (p[0], p[1], p[2].msg_id))
        evidence: list[EvidenceItem] = []
        provenance: list[EvidenceProvenance] = []
        used: list[Envelope] = []
        for _, _, m, expect, hid in picks:
            if m in used or len(evidence) >= self.max_items:
                continue
            p: CluePayload = m.payload
            provenance.append(
                EvidenceProvenance(
                    evidence_index=len(evidence),
                    clue_id=m.msg_id,
                    agent=m.sender,
                    entity_id=p.entity.entity_id,
                    unit=p.unit,
                    reference_value=p.comparison.reference_value,
                    config_key=p.comparison.config_key,
                    observation_ids=p.source_observation_ids,
                )
            )
            evidence.append(
                EvidenceItem(
                    metric=p.metric, value=float(p.value), interpretation=interpret(p, expect, hid)
                )
            )
            used.append(m)
        return evidence, provenance, used

    def _affected(
        self, winner: Candidate | None, focus: list[Candidate], used: list[Envelope]
    ) -> list[str]:
        roots = [c.root for c in ([winner] if winner else focus)]
        if winner is None:
            return list(dict.fromkeys(roots))
        symptoms = [m.payload.entity.entity_id for m in used if m.payload.significant]
        symptoms += [
            m.payload.observed_from
            for m in used
            if m.payload.significant and m.payload.observed_from
        ]
        return list(dict.fromkeys([*roots, *symptoms]))

    # ------------------------------------------------------------------ text
    def _describe(self, c: Candidate) -> str:
        h = self.cat.hypotheses[c.hypothesis_type]
        return f"{c.hypothesis_type} at {c.root}: {h.description}"

    def _cause(self, v: VerdictPayload, winner: Candidate | None, focus: list[Candidate]) -> str:
        if winner is not None:
            return self._describe(winner)
        if v.decision is Decision.NO_FAULT_DETECTED:
            return "no fault detected: no significant deviation matches any fault signature"
        if focus:
            names = " or ".join(f"{c.hypothesis_type} at {c.root}" for c in focus)
            return f"insufficient evidence to name a root cause; best explanations: {names}"
        return "insufficient evidence to name a root cause"

    def _fill(self, template: str, c: Candidate, idx: Any) -> str:
        topo = idx.topo
        link = topo.links.get(c.root)
        if link is not None:
            up, down = link.a, link.b
        else:
            preds = list(topo.graph.predecessors(c.root)) if c.root in topo.graph else []
            up, down = (preds[0] if preds else c.root), c.root
        return template.format_map(
            {"root": c.root, "upstream": up, "downstream": down, "scope": c.root}
        )

    def _actions(
        self,
        v: VerdictPayload,
        winner: Candidate | None,
        focus: list[Candidate],
        idx: Any,
        ctx: Context,
    ) -> list[str]:
        if winner is not None:
            return [
                self._fill(a, winner, idx)
                for a in self.cat.hypotheses[winner.hypothesis_type].actions
            ]
        if v.decision is Decision.NO_FAULT_DETECTED:
            scope = (
                idx.topo.payload.upstream_root
                if idx.topo.payload and idx.topo.payload.upstream_root
                else "the network"
            )
            return [a.format_map({"scope": scope}) for a in self.no_fault_actions]
        out = [self.collect_prefix + m for m in v.missing_evidence[:3]]
        for c in focus:
            first = self.cat.hypotheses[c.hypothesis_type].actions[0]
            out.append(
                self.if_prefix.format_map({"cause": f"{c.hypothesis_type} at {c.root}"})
                + self._fill(first, c, idx)
            )
        return out

    def _alternatives(
        self, v: VerdictPayload, winner: Candidate | None
    ) -> tuple[list[str], list[ScoredAlternative]]:
        merged = {
            line.split(" ")[1]: line.split(" into ")[1].split(" ")[0]
            for line in v.rationale
            if line.startswith("merged ")
        }
        alts, scored = [], []
        contenders = set()
        for line in v.rationale:
            if line.startswith("contenders: "):
                contenders = set(line.removeprefix("contenders: ").split(" vs "))
        for r in v.ranking:
            root = next((e.entity.entity_id for e in r.entities if e.role is EntityRole.ROOT), "?")
            key = key_of(r.hypothesis_type, root)
            if winner is not None and key == winner.key:
                continue
            if r.confidence < self.alt_min and key not in merged and key not in contenders:
                continue
            text = f"{r.hypothesis_type} at {root}"
            if key in merged:
                text += f" (explained by {merged[key]})"
            alts.append(text)
            scored.append(ScoredAlternative(cause=text, score=r.score, confidence=r.confidence))
        return alts, scored

    # ------------------------------------------------------------------ extensions
    def _breakdown(self, c: Candidate | None) -> list[ScoreTerm]:
        if c is None or self.model is None:
            return []
        t = self.model.tables["types"][c.hypothesis_type]
        h: HypothesisSpec = self.cat.hypotheses[c.hypothesis_type]
        out = [
            ScoreTerm(
                term=f"prior ({c.hypothesis_type})",
                status=f"{t['n_true']} true / {t['n_false']} false training candidates",
                contribution=round(t["prior_logit"], 4),
            )
        ]
        for e, s, llr in zip(h.signature, c.statuses, t["elements"], strict=True):
            out.append(
                ScoreTerm(
                    term=f"{e.metric} {e.expect} {e.direction} @ {e.scope} ({e.role})",
                    status=s,
                    contribution=round(llr[s], 4),
                )
            )
        out.append(
            ScoreTerm(
                term="analytic stance (topology)",
                status=c.analytic,
                contribution=round(self.model.tables["analytic"][c.analytic], 4),
            )
        )
        b = qbin(c.quality, self.model.quality_cutoffs)
        out.append(
            ScoreTerm(
                term="evidence quality",
                status=f"bin {b} (quality {c.quality:.2f})",
                contribution=round(self.model.tables["quality"][str(b)], 4),
            )
        )
        return out

    def _quality(self, board: Board, ctx: Context, affected: list[str]) -> DataQualitySummary:
        per: dict[str, list[float]] = {}
        issues: Counter[str] = Counter()
        for m in board.query(type=T.OBSERVATION):
            o = m.payload
            issues.update(o.quality.issues)
            for e in (o.entity.entity_id, o.observed_from):
                if e in affected:
                    per.setdefault(e, []).append(o.quality.score)
        return DataQualitySummary(
            overall=round(ctx.mean_quality, 6),
            per_entity={k: round(fmean(v), 6) for k, v in sorted(per.items())},
            issues=dict(sorted(issues.items())),
        )

    def _simulate(
        self, winner: Candidate, actions: list[str], used: list[Envelope]
    ) -> tuple[SimulatedAction, ...]:
        effects = []
        for m in used:
            p: CluePayload = m.payload
            if not p.significant:
                continue
            where = p.entity.entity_id + (f" (from {p.observed_from})" if p.observed_from else "")
            if p.statistic is Statistic.SLOPE:
                effects.append(f"{p.metric} on {where} stops rising")
            elif p.statistic is Statistic.FRACTION:
                effects.append(f"{p.metric} on {where} returns to a healthy state")
            elif isinstance(p.comparison.reference_value, int | float):
                kind = "baseline" if p.comparison.basis is ComparisonBasis.BASELINE else "threshold"
                effects.append(
                    f"{p.metric} on {where} returns from {float(p.value):.3g} to about "
                    f"{float(p.comparison.reference_value):.3g} {p.unit} ({kind})"
                )
        effects = list(dict.fromkeys(effects)) or [
            f"symptoms of {winner.hypothesis_type} at {winner.root} clear"
        ]
        return tuple(SimulatedAction(action=a, expected_effects=tuple(effects)) for a in actions)

    def _limitations(
        self, board: Board, run: RunInfo, v: VerdictPayload, ctx: Context, used: list[Envelope]
    ) -> tuple[str, ...]:
        out = list(base_limitations(board, run))
        for m in used:
            if m.payload.data_quality < self.low_q:
                out.append(
                    f"low-quality evidence: {m.payload.metric} on {m.payload.entity.entity_id} "
                    f"(quality {m.payload.data_quality:.2f} < {self.low_q:.2f})"
                )
        if ctx.unassessable:
            out.append(
                "could not assess (required metrics not observed or not analysed): "
                + ", ".join(ctx.unassessable)
            )
        if ctx.not_applicable:
            out.append(
                "not applicable (no possible root in the data): " + ", ".join(ctx.not_applicable)
            )
        if v.method == "courtroom" and v.decision is not Decision.DIAGNOSED:
            ruling = next((r for r in v.rationale if r.startswith("ruling: ")), "")
            out.append("courtroom deferred: " + ruling.removeprefix("ruling: "))
        return tuple(dict.fromkeys(out))
