# Reporting

Every run writes `runs/<incident_id>/report.json` and `report.md`, and posts a REPORT message
whose causation is the final VERDICT. Examples (generated, committed):

- [diagnosed link congestion](../4_sample_data_and_test_cases/example_reports/diagnosed_link_congestion.md) ([json](../4_sample_data_and_test_cases/example_reports/diagnosed_link_congestion.json))
- [diagnosed DNS failure](../4_sample_data_and_test_cases/example_reports/diagnosed_dns_failure.md) ([json](../4_sample_data_and_test_cases/example_reports/diagnosed_dns_failure.json))
- [hardware failure, deferred by the courtroom](../4_sample_data_and_test_cases/example_reports/deferred_hardware_failure.md) ([json](../4_sample_data_and_test_cases/example_reports/deferred_hardware_failure.json))

## report.json

The top-level keys are **exactly** the organiser's A7 shape. Everything NetCoop adds sits
under the single key `x_netcoop`. A test checks this on every generated run (1,200 of 1,200
runs pass, Phase 7).

| A7 key | how it is produced |
|---|---|
| `status` | `diagnosed`, `insufficient_evidence` or `no_fault_detected` (`failed` is reserved for runs that cannot complete), from the final VERDICT (the correlator's, or the judge's after a courtroom) |
| `suspected_root_cause` | `<fault> at <root>: <catalogue description>`. When nothing is asserted, the best explanations are named as such |
| `confidence` | calibrated confidence **in what is asserted**: the root cause, or "no fault". It is `0.0` when nothing is asserted (the contenders' confidences are in `x_netcoop.alternatives_scored`) |
| `affected_devices` | the root, then the locations of significant evidence (entities and probe vantage points). When nothing is asserted, the contenders' roots |
| `supporting_evidence` | from the correlator's **recomputed** signature of the reported candidate: satisfied elements, required ones first, then by deviation. At most `evidence.max_items`. Includes "stayed normal" evidence where the fault predicts normality (e.g. healthy transport for a DNS failure) |
| `interpretation` | generated from the clue's evidence model: statistic, value and unit, direction, the reference and its basis (calibrated baseline, cited threshold, or the series' own earlier level), the normalised deviation and its unit, persistence, data quality and the config key |
| `alternative_causes` | other candidates with calibrated confidence ≥ `alternatives.min_confidence`, plus causally merged candidates ("explained by …") and courtroom contenders |
| `recommended_actions` | catalogue actions filled with the real entities (`{root}`, `{upstream}`, `{downstream}`). When nothing is asserted: data-collection steps for the missing evidence, plus each contender's first action prefixed "If … is confirmed:". For no fault: monitoring actions from config |
| `evidence_sources` | the agents whose clues are cited, plus the correlator; Connectivity when its analytic stance counted; prosecutor, defense and judge after a courtroom |
| `limitations` | Translator and agent ERRORs, failed or inactive (required) agents, non-convergence, unassessable and not-applicable fault types, evidence below `quality.low_threshold`, courtroom deferrals |

### x_netcoop

| field | content |
|---|---|
| `confidence_category` | `high`, `medium` or `low` (SCORING.md §4); `none` when nothing is asserted |
| `evidence_provenance` | per evidence item: clue id, agent, entity, unit, reference value, config key and source observation ids. Every observation id resolves to an OBSERVATION in the trace (tested) |
| `score_breakdown` | the itemised log-odds of the reported (or best) candidate: prior with its training counts, each signature element's status and LLR, the analytic stance, the evidence-quality bin |
| `alternatives_scored` | alternatives with raw score and calibrated confidence |
| `data_quality` | overall quality, per affected entity, and counts of every quality issue code |
| `courtroom` | contenders, rounds, outcome (resolved or deferred), both briefs and the ruling, and the transcript message ids |
| `missing_evidence` | what would resolve an abstention |
| `simulated_remediation` | per action, the expected effects if the diagnosis is right, e.g. "utilization on L returns from 91.5 to about 27.4 percent (baseline)". `applied` is always false: nothing is ever executed |
| `manifest` | input, config and code identity, protocol and vocabulary versions, seed |

## report.md

The same data rendered as Markdown:

- status, cause and confidence
- affected entities
- the evidence table, with the agent behind each item
- the log-odds breakdown
- alternatives with their confidences
- the courtroom summary
- actions, each with its simulated effect
- missing evidence
- limitations
- data quality
- provenance

Rendering is a deterministic template. An LLM could later polish the wording of this file
only. It never sees or changes `report.json`, so diagnoses are identical with or without it
(C1.8).
