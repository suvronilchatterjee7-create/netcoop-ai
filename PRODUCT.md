# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

No new dependencies: Python's standard-library HTTP server (`netcoop serve`) serving one
static HTML/CSS/JS page plus a small JSON API over the existing `netcoop` package. Chosen by
the user so the dashboard works right after `pip install -e .` with no build step.

## Users

Primary: hackathon judges (IIT Bhubaneswar Agentic AI Hackathon) watching a 3-5 minute demo
video or running the project themselves. They need to see, quickly and credibly, how
cooperating agents reach a diagnosis and why the system can be trusted. Secondary: network
operators diagnosing an incident.

## Product Purpose

NetCoop AI diagnoses network faults with cooperating specialist agents that exchange typed,
versioned messages on a shared case board, and produces one explainable report: root cause,
calibrated confidence, evidence traced to raw telemetry, affected devices and recommended
actions, or an honest `insufficient_evidence`. The dashboard makes that process visible: run a
diagnosis live, watch the agents' messages, read the report.

## Positioning

Precision over coverage: 98.6% of claims are correct on 1,080 fresh test runs, because the
system abstains instead of guessing. Every conclusion is traceable to messages and raw
observations, and a courtroom tie-break argues competing explanations from discriminating
evidence only.

## Operating Context

- Inputs are run folders of telemetry (native JSONL or legacy CSV); nine labelled samples ship
  in `data/samples/`.
- Every run writes `runs/<incident>/` with `report.json`, `report.md`, `trace.jsonl` and
  `manifest.json`.
- The demo video follows `docs/DEMO_SCRIPT.md`; the terminal `netcoop demo` covers the same
  scenes.

## Capabilities and Constraints

- Statuses: `diagnosed`, `insufficient_evidence`, `no_fault_detected`.
- Message types include CAPABILITY, TOPOLOGY, OBSERVATION, CLUE, HYPOTHESIS, REQUEST,
  RESPONSE, SUPPORT, CONTRADICT, VERDICT, REPORT, ERROR, ACK.
- Agents: translator, performance, infrastructure, wireless_service, connectivity,
  correlator, prosecutor, defense, judge, reporter.
- Diagnoses are deterministic; a run takes a few seconds.
- Remediation is simulated only; recommendations are never executed.
- Local only: no accounts, no network services.

## Evidence on Hand

- docs/EVALUATION.md (headline metrics, slices, ablations), docs/COURTROOM_RESULTS.md,
  docs/INTEROP_RESULTS.md.
- Real reports from the sample runs. No testimonials, users or deployments exist; never
  fabricate them.

## Product Principles

1. Show the reasoning, not just the answer: the message chain is the product.
2. Honesty is a feature: abstentions and deferred rulings are presented as outcomes, not
   failures.
3. Everything shown traces back to a real message, observation or document.
4. Legible on a screen recording: one incident at a time, readable at a glance.
