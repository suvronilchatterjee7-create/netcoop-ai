# Working prototype

NetCoop runs locally with Python 3.11+. It has two front ends over the same pipeline: a
**command line** and a **local web dashboard**.

## Setup (from the repository root)

```bash
python -m venv .venv
```

Activate it (`.venv\Scripts\activate` on Windows, `source .venv/bin/activate` elsewhere), then:

```bash
pip install -e ".[dev]"
```

The fitted model, baselines and nine sample runs are already in the repository. Nothing has to
be generated or trained first.

## Dashboard

```bash
netcoop serve
```

It opens **http://127.0.0.1:8765/** and only listens on your own machine.

1. Pick a sample run on the left.
2. Press **Diagnose**. Fig. 1 fills in live as the agents post messages: one lane per agent,
   numbered points, and lines from each message to its cause.
3. Read the report: root cause, calibrated confidence, evidence, actions, affected devices,
   courtroom ruling, data quality and references. Hover a red citation number to light up the
   message that proves the claim.
4. The **Past runs** and **Evaluation** tabs list earlier diagnoses and the test-suite results.

## Command line

| command | what it does |
|---|---|
| `netcoop run <run folder> -v` | full pipeline, printing every board message |
| `netcoop replay runs/<incident>` | rebuild the board from its trace and verify it |
| `netcoop translate <run folder>` | show how raw telemetry is read, and any typed errors |
| `netcoop demo --step` | six scripted scenes in the terminal |
| `netcoop mcp` | serve NetCoop to other AI agents over MCP |

Each run writes `runs/<incident>/` containing:
- `report.json` and `report.md`, the final diagnostic report
- `trace.jsonl`, every message
- `manifest.json`, the hashes for reproducibility

## The complete workflow

1. **Telemetry.** The Translator reads raw files in any supported format and posts canonical
   observations.
2. **Agents.** The specialists post clues and hypotheses, request evidence from each other, and
   take stances.
3. **Diagnosis.** The correlator scores every candidate and claims a cause only above the
   calibrated bar. The courtroom settles near ties.
4. **Report.** The reporter publishes one report, with every piece of evidence traced to its
   source.

## Screenshots: `screenshots/`

| file | shows |
|---|---|
| `01_dashboard_start.jpg` | the dashboard before a run |
| `02_live_diagnosis_fig1.jpg` | Fig. 1, the agents' message exchange, after a live run |
| `03_report_citation_hover.jpg` | the final report; hovering a citation highlights its message |
| `04_report_evidence_actions.jpg` | evidence, recommended actions, affected devices |
| `05_legacy_csv_translate.jpg` | a legacy CSV export read with zero errors |
| `06_abstention_not_enough_evidence.jpg` | an honest abstention on a faint fault |
| `07_courtroom_resolved.jpg` | courtroom tie-break, resolved |
| `08_courtroom_deferred.jpg` | courtroom deferring on a fault type never seen in training |
| `09_cli_trace_replay.jpg` | the command line printing every board message |
| `10_evaluation.jpg` | evaluation results on 1,080 fresh test runs |
