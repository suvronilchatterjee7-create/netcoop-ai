# Changelog

## [Unreleased]

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
