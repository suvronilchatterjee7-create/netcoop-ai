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

## D-004 · 2026-11-01 · Provisional stand-in generator
**Context:** The organiser's Colab generator is not available to the team.
**Decision:** Build `generator/synth.py` behind the existing adapter interface. It simulates a
three-tier campus (core, per-zone distribution/access switches, APs, DNS/DHCP servers), injects
one fault family with ramped onset, and emits two dialects (`netcoop_synth_v2` JSONL and
`legacy_v1` CSV). The legacy dialect is used for the `interop_failure` family, layered on a
random underlying network state, so interop is tested *together with* diagnosis.
**Guardrails:** `netcoop/` never imports the generator; its parameters live in
`config/synthetic_generator.yaml` and are never read by the diagnosis engine; detection
thresholds will be derived from data (`calibrate`) or cited references, not copied from the
generator config. Phase 2's mutator adds further dialect/corruption variety independently.
**Risk:** a self-written generator can make the engine look better than it is (we know the
signatures). Mitigations: noise and missing-data sweeps, mutator corpus, held-out seeds, and
swapping in the organiser's generator via `generator/adapter.py` as soon as it is released.

## D-005 · 2026-11-01 · Sweep size reduced to 5 seeds
**Why:** measured ~123 MB and ~10 s per seed (216 runs). 5 seeds = 1080 runs, ~610 MB, ~50 s.

## Open questions
- **Q-001** ~~Sweep sizes~~ resolved by D-005.
- **Q-002** Canonical schema: derive from `docs/DATA_PROFILE.md` (Phase 1). Re-check if the
  organiser generator is later provided.
- **Q-003** Ask the organisers whether their generator will be released; if so, re-run
  `make generate && make profile` and diff the profile against the current one.
