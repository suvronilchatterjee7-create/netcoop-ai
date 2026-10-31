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

## D-006 · 2026-11-01 · Content-hash message ids
**Why:** deterministic traces (C1.8) and free duplicate detection on the board. Timestamp is
excluded from the hash so re-runs give identical ids. **Trade-off:** two genuinely distinct
but byte-identical posts collapse into one, which is the desired idempotency.

## D-007 · 2026-11-01 · Report status values
A7 lists `diagnosed | insufficient_evidence | ...`. We add `no_fault_detected` (normal operation
is a first-class outcome, not "diagnosed: normal") and `failed` (the run itself could not
complete). NetCoop fields go in a single `x_netcoop` key so the A7 keys are untouched.

## D-008 · 2026-11-01 · Protocol 1.0 "lite" profile and assumed quality
To exercise and demonstrate version negotiation, 1.0 is defined as a minimal profile for
simple/external agents (PROTOCOL.md §6.1). Upgraded messages get
`v1_upgrade.assumed_data_quality` (0.5, maximum-entropy midpoint) and an explicit
`quality_unknown_v1` issue. **Open:** revisit the value once correlator weights are fitted.

## D-009 · 2026-11-01 · Observations are time series, not single samples
One OBSERVATION = one metric on one entity over the window (~600 messages per incident rather
than ~20k). Evidence still cites observations by id, and per-sample provenance is preserved
through `Point.src`.

## D-010 · 2026-11-01 · Interop failure is not a hypothesis type
Interoperability problems are about the data, not the network. They are handled by the
Translator (typed errors, quality scores, limitations). The network root cause underneath is
still diagnosed. Evaluation of the `interop_failure` family therefore scores the underlying
root cause plus successful recovery.

## D-011 · 2026-11-01 · DNS and DHCP are separate hypothesis types
They have different remedies and different evidence, so they are proposed separately. Both map
to the `dns_dhcp_failure` scenario family for evaluation.

## D-012 · 2026-11-01 · Wired vs wireless loss are distinct metrics
`packet_loss` (links) and `wireless_packet_loss` (APs). The native dialect reuses one field
name for both; the Translator disambiguates by record kind.

## D-013 · 2026-11-01 · Mapping-certainty levels are ordinal judgements
The values exact 1.0, normalised 0.95, suffix 0.95, inferred 0.7 and unresolved entity 0.6
(config/translator.yaml) encode an ordering we can defend (exact > lossless guess > plausibility
guess > unplaceable). Their exact magnitudes cannot be derived from data yet. **Open:** Phase 8
sensitivity analysis; Phase 5 may fit them.

## D-014 · 2026-11-01 · Alias-based mapping; dialect detection is for reporting only
Mapping does not branch on dialect. Every field goes through one alias table, so mixed or
unseen dialects work whenever their names are covered. Dialect profiles exist only to label
provenance and to check schema versions. **Alternative rejected:** per-dialect mapping files,
which fail on any unseen variant (renamed field, partial upgrade).

## D-015 · 2026-11-01 · Robust reference time
Reference time = median of per-source newest timestamps (not the maximum), and the interval
is the median sampling interval. A single shifted source then cannot make all others look
stale, and it gets the `CLOCK_SKEW` flag itself.

## D-016 · 2026-11-01 · Per-sample provenance
Every point keeps a `SourceRef` (file, line or row, original field name), so any report
statement can be traced to a line of raw input. Cost: ~2 MB of trace per incident, which is
acceptable.

## D-017 · 2026-11-01 · Suggestions never applied
Fuzzy matches for unknown fields appear only as `suggestion` in the `UNKNOWN_FIELD` error
(Part D Phase 2.2). Applying them would turn a visible data problem into a silent wrong value.

## D-018 · 2026-11-01 · Topology vs telemetry classification
A table is topology only if it has endpoint columns, no timestamp and no metric fields other
than capacity. Found by the mutator: without the metric rule, a link table that lost its
timestamp column was silently read as topology instead of raising `MISSING_FIELD`.

## Open questions
- **Q-001** ~~Sweep sizes~~ resolved by D-005.
- **Q-002** Canonical schema: derive from `docs/DATA_PROFILE.md` (Phase 1). Re-check if the
  organiser generator is later provided.
- **Q-003** Ask the organisers whether their generator will be released; if so, re-run
  `make generate && make profile` and diff the profile against the current one.
