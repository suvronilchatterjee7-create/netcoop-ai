"""Human-readable rendering of a Report (report.md). Same data as report.json, nothing added.

Deterministic template rendering. An optional LLM could polish wording later, but it would
only rephrase this text; it would never change the diagnosis (Part C1.8).
"""

from __future__ import annotations

from netcoop.protocol.report import Report

_STATUS = {
    "diagnosed": "Diagnosed",
    "insufficient_evidence": "Insufficient evidence",
    "no_fault_detected": "No fault detected",
    "failed": "Run failed",
}


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render(report: Report) -> str:
    x = report.x_netcoop
    lines = [
        f"# Incident {report.incident_id}",
        "",
        f"**Status:** {_STATUS.get(report.status.value, report.status.value)}  ",
        f"**Root cause:** {report.suspected_root_cause}  ",
        f"**Confidence:** {report.confidence:.2f}" + (f" ({x.confidence_category})" if x else ""),
        "",
    ]
    if report.affected_devices:
        lines += ["## Affected", "", ", ".join(f"`{d}`" for d in report.affected_devices), ""]
    if report.supporting_evidence:
        lines += [
            "## Evidence",
            "",
            "| # | metric | value | interpretation | agent |",
            "|---|---|---|---|---|",
        ]
        prov = {p.evidence_index: p for p in x.evidence_provenance} if x else {}
        for i, e in enumerate(report.supporting_evidence):
            agent = prov[i].agent if i in prov else ""
            lines.append(
                f"| {i + 1} | {e.metric} | {e.value:.4g} | {_cell(e.interpretation)} | {agent} |"
            )
        lines.append("")
    if x and x.score_breakdown:
        lines += [
            "## Why (log-odds of the reported candidate)",
            "",
            "| component | status | contribution |",
            "|---|---|---|",
        ]
        lines += [
            f"| {_cell(t.term)} | {_cell(t.status)} | {t.contribution:+.2f} |"
            for t in x.score_breakdown
        ]
        lines.append("")
    if report.alternative_causes:
        lines += ["## Alternative explanations", ""]
        scored = {a.cause: a for a in x.alternatives_scored} if x else {}
        for a in report.alternative_causes:
            conf = f" (confidence {scored[a].confidence:.2f})" if a in scored else ""
            lines.append(f"- {a}{conf}")
        lines.append("")
    if x and x.courtroom and x.courtroom.invoked:
        c = x.courtroom
        lines += [
            "## Courtroom",
            "",
            f"Contenders: {' vs '.join(c.contenders)}. Outcome: **{c.outcome}** "
            f"after {c.rounds} round(s); {len(c.transcript_msg_ids)} transcript messages.",
            "",
        ]
        lines += [f"- {part}" for part in c.summary.split(" | ")] + [""]
    if report.recommended_actions:
        lines += ["## Recommended actions (for human review)", ""]
        sims = {s.action: s for s in x.simulated_remediation} if x else {}
        for i, a in enumerate(report.recommended_actions, 1):
            lines.append(f"{i}. {a}")
            if a in sims:
                lines.append(
                    f"   - *Simulated (not applied):* expect {'; '.join(sims[a].expected_effects)}"
                )
        lines.append("")
    if x and x.missing_evidence:
        lines += ["## Missing evidence", "", *[f"- {m}" for m in x.missing_evidence], ""]
    if report.limitations:
        lines += ["## Limitations", "", *[f"- {_cell(m)}" for m in report.limitations], ""]
    if x and x.data_quality:
        q = x.data_quality
        lines += [
            "## Data quality",
            "",
            f"Overall {q.overall:.2f}."
            + (
                " Affected entities: "
                + ", ".join(f"`{k}` {v:.2f}" for k, v in q.per_entity.items())
                + "."
                if q.per_entity
                else ""
            )
            + (
                " Issues: " + ", ".join(f"{k} x{v}" for k, v in q.issues.items()) + "."
                if q.issues
                else ""
            ),
            "",
        ]
    lines += ["## Provenance", "", f"Evidence from: {', '.join(report.evidence_sources) or '-'}."]
    if x and x.manifest:
        m = x.manifest
        lines.append(
            f"Input `{m.input_hash[:12]}`, config `{m.config_hash[:12]}`, code {m.code_version}, "
            f"protocol {m.protocol_version}, vocabulary {m.vocabulary_version}, seed {m.seed}."
        )
    return "\n".join(lines) + "\n"
