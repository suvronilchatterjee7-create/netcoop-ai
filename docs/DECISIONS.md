# Decision log

Format: ID · date · decision · why · alternatives considered.

## D-001 · 2026-10-31 · Config values must carry `{value, unit, rationale, source}`
**Why:** Enforces Part C1.1 mechanically; `netcoop.config.load_config` rejects bare scalars.
**Alternatives:** convention-only review (easy to slip under time pressure).

## D-002 · 2026-10-31 · Generator integrated through `generator/adapter.py`
**Why:** The organiser's notebook API is not known yet. A single adapter function isolates it,
so the sweep, ground-truth metadata and directory layout do not depend on guessed names.
**Alternatives:** porting the notebook directly into `netcoop/` (couples us to its internals).

## D-003 · 2026-10-31 · Train/holdout split by seed, not by record
**Why:** Records from one generator draw are correlated; splitting by seed avoids leakage
into calibration and evaluation.

## Open questions
- **Q-001** Sweep sizes in `config/generation.yaml` (10 seeds, 4 intensities, 3 noise, 3 missing)
  are placeholders until the generator's runtime and native parameters are known.
- **Q-002** Canonical schema: blocked on `docs/DATA_PROFILE.md` from real generator output.
