# Changelog

## [Unreleased]

### Phase 0 — Foundation
- Repository layout, `pyproject.toml`, `Makefile`, `.gitignore`, README skeleton.
- `netcoop.config`: loader that enforces justified parameter entries.
- `netcoop.generation`: sweep runner with ground-truth `meta.json` per run, via a generator adapter.
- `netcoop.profiling` + `netcoop profile`: schema-agnostic field inventory into `docs/DATA_PROFILE.md`.
- `netcoop` CLI with `generate` and `profile`; `run`, `replay`, `calibrate`, `eval` stubbed.
