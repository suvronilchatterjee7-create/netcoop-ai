---
version: 1
slug: "netcoop-web-static-index-html"
primary_target: "netcoop/web/static/index.html"
related_targets: ["netcoop/web/static/app.js","netcoop/web/static/app.css"]
---

## Scope

NetCoop dashboard (`netcoop serve`), one page. Mode: Operate. Audience: hackathon judges watching a demo
video or running it locally; secondary, operators. Task: pick a run folder, diagnose it, watch the
agents' messages arrive, read the report and see why it is trusted. States: idle (nothing selected),
running (live stream), diagnosed, insufficient_evidence, no_fault_detected, courtroom resolved and
deferred, failed run, server unreachable, empty past-runs list.

## Direction contract

THESIS: A diagnosis published like a research paper: every claim in the report carries a numbered
citation to the board message that proves it, and Fig. 1 plots how the agents got there. Refuses the
category default of status cards over a log table.

OWN-WORLD: White journal page, ink #16181d, a journal-blue shell (#1f3a7a top bar, tinted #f5f7fb
rail). Citation red #c8361b used only for citation marks and the cited point's highlight. Agent series
colours as figure series (performance teal, infrastructure ochre, wireless violet, connectivity blue,
correlator ink, courtroom crimson). Source Serif 4 for the report's prose; Public Sans for UI and data.
Hairline rules, no cards, no shadows.

STORY: The viewer picks a sample, presses Diagnose, sees Fig. 1 fill lane by lane, then reads one
headline claim with its proofs one click away, and believes it because each number lights the message.

FIRST VIEWPORT: Top bar (product, Diagnose/Runs/Evaluation tabs). Left rail 280px: samples, then past
runs. Centre: report (kicker, serif headline root cause, status/confidence line, abstract with
superscripts, evidence, actions, alternatives, courtroom ruling). Right 500px: Fig. 1 swimlanes (agent
lanes × rounds), counts strip, caption. Primary action: Diagnose button in the report header.
Signature interaction: hovering or focusing a superscript highlights the cited point in Fig. 1 and shows
the message; clicking a point scrolls to every claim that cites it.

FORM: Journal of Record, position 4 of 7 on the ordered list; seed:b8de3996af07ab93.

Raises: citation red does one job (from Terminal Wayfinding); one lane per agent, time on one axis
(from Labanotation); one visible column grid for rail, report and figure (from Crouwel).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
