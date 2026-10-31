# Changelog

## [Unreleased]

### Phase 9 — Optional enhancements
- Pause/resume: `netcoop run --pause-after N` and `netcoop resume`; resumed traces are
  byte-identical to uninterrupted runs.
- Human review: `netcoop review` (approve/reject with reviewer and note), recorded as ACK
  messages in the verified trace and in report.md.
- Extension points: `NETCOOP_EXTENSIONS` (vocabulary, catalogue and agent drop-ins, plus
  `plugins/*.py`) and `NETCOOP_PLUGINS`; pooled-LLR fallback for fault types without training
  data. Worked example in `examples/extension/` (ap_client_overload and a client_load agent).
- MCP server: `netcoop mcp` (tools: diagnose, translate, list_runs, get_report, get_trace,
  get_topology, review_actions; resources: schema, vocabulary, catalogue); external-agent
  bridge accepting protocol 1.0 lite or 2.0.
- Vocabulary fix: `associated_clients` has `worse_when: higher`; model refitted.
- Docs: EXTENDING.md, ORCHESTRATION.md pause/resume/review section, decisions D-046 to D-049.

### Phase 8 — Evaluation, robustness and testing
- `netcoop.evaluation`: parallel harness over configurations; metrics (accuracy, precision of
  claims, macro-F1, confusion matrix, root and affected-set localisation, abstention
  precision/recall, calibration); slices by missing rate, noise, intensity and family; a
  stacked-mutation robustness curve; ablations (no courtroom, no corroboration, no connectivity,
  single agents); the unseen-fault suite.
- `netcoop eval` (and `--quick`) generates the fresh test suite (seeds 500-504) and writes
  docs/EVALUATION.md.
- Correlator `corroboration` ablation switch; mutator robust to stacked mutations.
- Fix (D-043): fatal input/agent errors block 'no fault' claims.
- Acceptance-gate test for every A10 criterion; property-based Translator tests.
- CI workflow (.github/workflows/ci.yml): ruff, mypy, schema freshness, pytest with coverage
  (84%). Makefile `fit`, `eval`, `quick-eval`; `test` reports coverage.
- Decisions D-042 to D-045.

### Phase 7 — Reporting
- `netcoop.reporting.reporter.Reporter` (now the default): evidence from the recomputed
  signature, interpretations generated from each clue's evidence model, catalogue actions
  filled with real entities, conditional actions and data collection when abstaining,
  aggregated limitations, confidence in the asserted outcome.
- Report extensions: `score_breakdown` (itemised log-odds), `simulated_remediation` (dry run),
  data-quality summary, courtroom summary.
- `netcoop.reporting.markdown`: `report.md` next to `report.json` in every run directory.
- `config/reporting.yaml`; example reports in docs/examples/.
- Verified: 1,200 of 1,200 generated runs (main + ambiguity suites) give schema-valid A7
  reports with every evidence item traced to observations.
- Docs: REPORTING.md, decisions D-039 to D-041.

### Phase 6 — Courtroom tie-break
- `netcoop.courtroom`: prosecutor / defense / judge. Discriminating-evidence briefs on
  differential scopes (signature semantics, independence, quality weighting), discovery
  REQUESTs by capability, stance arguments, bounded rounds, and a ruling that confirms,
  accepts a calibrated contender, or defers.
- Correlator opens a case on a near tie or on an under-trained, related, overlapping
  contender; the orchestrator runs the courtroom stage (specialists answer its requests), and
  the judge's VERDICT follows the correlator's preliminary one.
- Report `x_netcoop.courtroom` summary (contenders, rounds, outcome, briefs, transcript ids).
- Generator: hardware_failure and device_overload injection for the ambiguity suite (fresh
  seeds, outside the main sweep). Vocabulary families for both.
- Trend tests use the recent window (D-035); correlation model refitted.
- `netcoop courtroom-eval`: ablation with vs without the courtroom -> docs/COURTROOM_RESULTS.md.
- Docs: COURTROOM.md, SCORING.md section 5, decisions D-034 to D-038.

### Phase 5 — Fault correlation
- `netcoop.agents.signature`: signature assessment shared by specialists and the correlator,
  with observation-level independence.
- `netcoop.correlation.features`: candidate extraction (merged proposals, recomputed
  signatures, analytic stances, evidence quality) and context (observed vs assessed metrics,
  unassessable faults).
- `netcoop.correlation.model`: naive-Bayes LLR tables with shrinkage, Platt calibration,
  log-odds ranking, causal-precedence merging, decision policy (diagnosed, near tie,
  insufficient evidence, no fault).
- `netcoop fit`: parallel pipeline over training seeds, fit, threshold grid search at the
  target precision; writes config/correlation.yaml and docs/CALIBRATION.md (held-out Brier,
  ECE, reliability, decisions by family, missing rate and noise).
- `netcoop.correlation.correlator.Correlator` is now the orchestrator's default; confidence
  categories are tied to the fitted operating points.
- Docs: SCORING.md section 4, CALIBRATION.md, decisions D-029 to D-033.

### Phase 4 — Specialist agents
- `netcoop.detection`: calibrated percentile bands with robust z, cited thresholds with a
  standard-error gate, an in-window median-shift test with AR(1)-corrected SE, Mann-Kendall
  and Theil-Sen trends, enum-state fractions, and a persistence requirement.
- `netcoop calibrate`: derives `config/baselines.yaml` from training-seed normal runs only,
  each entry with a generated rationale and source.
- `config/catalogue/hypotheses.yaml`: 7 faults with locus, signature, scopes, relations,
  parametrised actions, rationale and source. `config/catalogue/agents.yaml` defines the specialists.
- Generic specialist engine (clues, proposals by scope inversion, capability requests,
  stances, responses); agents performance, infrastructure, wireless_service (optional) and
  connectivity (blast radius, lowest common upstream).
- `config.resolve_key`; config hash now covers config/catalogue.
- Docs: AGENTS.md, SCORING.md sections 2-3, decisions D-024 to D-028.

### Phase 3 — Case board and orchestrator
- `netcoop.board.Board`: append-only versioned store with idempotency, causal integrity,
  depth-based loop prevention, per-agent round budget, indexed queries and filtered subscriptions.
- `netcoop.agents.base` / `registry`: agent plugin interface (`card` + `step`), `AgentContext`
  (read board, deterministic `post`), self-registration and discovery.
- `netcoop.orchestrator`: version negotiation, activation by data, concurrent rounds with
  deterministic commit order, capability-routed REQUEST/RESPONSE (unsupported fallback),
  timeouts, failure isolation, convergence and round limit, closing correlation/report stages.
- Tracing: `runs/<incident>/trace.jsonl` (live), `manifest.json`, `report.json`; `replay` with
  full verification.
- `netcoop.api.diagnose` / `run_diagnosis` with an event hook; CLI `netcoop run`, `netcoop replay`.
- Provisional correlator (always abstains) and reporter (schema-valid A7 report).
- `Envelope` now declares `type` / `payload` for typed generic access.
- Docs: ORCHESTRATION.md, decisions D-019 to D-023.

### Phase 2 — Translator
- `data/mappings/canonical.yaml`: declarative aliases, entity bindings, enum values, topology
  fields and dialect profiles for both generator dialects plus common NMS names.
- `netcoop.translator`: schema-agnostic readers (CSV/JSON/JSONL, sniffing), topology ingestion,
  unit resolution (declared, suffix, plausibility-inferred), five validation layers, robust
  staleness and clock-skew detection, per-sample provenance, geometric-mean data quality, and
  aggregated typed errors. It never raises on input.
- `netcoop.mutation`: 22-kind interop mutator, checker and corpus runner.
- CLI: `netcoop translate`, `netcoop interop-eval` (writes docs/INTEROP_RESULTS.md).
- `load_config` caches by file mtime (Translator went from 4.3 s to 0.7 s per run).
- New error codes `DUPLICATE_SAMPLE`, `INAPPLICABLE_METRIC`.
- Docs: TRANSLATOR.md, SCORING.md §1, decisions D-013 to D-018.

### Phase 1 — Protocol
- Controlled vocabulary in `data/vocabulary/`: 19 canonical metrics with units, physical ranges
  and direction; unit conversion table; entity types; hypothesis types including `normal` and
  `insufficient_evidence`.
- `netcoop.protocol`: versioned envelope, 13 typed message types (discriminated union), evidence,
  hypothesis, stance, request/response, error, verdict and A7 report models, all validated against
  the vocabulary.
- Capability cards with routing (`wants`, `can_serve`, `is_active`).
- Protocol 1.0 "lite" profile with 1.0 <-> 2.0 adapters, shortest-path conversion and version negotiation.
- `netcoop schemas`: JSON Schemas in `docs/schemas/` and generated `docs/PROTOCOL_REFERENCE.md`.
- `docs/PROTOCOL.md` with rules, versioning, an annotated sequence and test-checked examples.

### Phase 0 — Foundation
- Repository layout, `pyproject.toml`, `Makefile`, `.gitignore`, README skeleton.
- `netcoop.config`: loader that enforces justified parameter entries.
- `netcoop.generation`: sweep runner with ground-truth `meta.json` per run, via a generator adapter.
- `netcoop.profiling` + `netcoop profile`: schema-agnostic field inventory into `docs/DATA_PROFILE.md`.
- `netcoop` CLI with `generate` and `profile`; `run`, `replay`, `calibrate`, `eval` stubbed.
- Provisional stand-in generator (`generator/synth.py`, D-004) behind `generator/adapter.py`:
  campus topology, five fault families plus interop layering, native JSONL and legacy CSV dialects.
- Generator ground truth merged into each run's `meta.json`; deterministic output verified.
- `docs/DATA_PROFILE.md` generated from 1080 runs; dialect mapping notes in `DATA_PROFILE_NOTES.md`.
