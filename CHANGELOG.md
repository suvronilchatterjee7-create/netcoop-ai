# Changelog

## [Unreleased]

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
