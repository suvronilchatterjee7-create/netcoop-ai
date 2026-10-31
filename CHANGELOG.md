# Changelog

## [Unreleased]

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
