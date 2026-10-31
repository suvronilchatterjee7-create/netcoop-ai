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

## D-019 · 2026-11-01 · Concurrent steps, ordered commits
Agents of a round run in parallel but commit in agent-id order after the round, so traces
are deterministic regardless of scheduling (C1.8). Cost: an agent cannot see another
agent's post from the same round. That is acceptable because rounds are cheap and convergence
is checked.

## D-020 · 2026-11-01 · Logical time for messages
Message timestamps are the data's reference time, not the wall clock. Wall-clock timing is
kept only in the manifest's `timing` block, outside the trace hash.

## D-021 · 2026-11-01 · Ingestion exempt from the flood budget
Found by test: the per-agent round budget also capped the Translator's round-0 posts, which
would silently drop observations on a large network. Ingestion and replay now post with
`budgeted=False`. Round-0 rejections are reported too.

## D-022 · 2026-11-01 · No per-message ACKs on the board
The board's accept/duplicate/reject result is returned to the poster directly, and rejections
are aggregated into ERRORs. Posting an ACK for each of ~500 messages would double the trace
for no information. ACK messages remain available for external agents and transports.

## D-023 · 2026-11-01 · Provisional correlator abstains
Until the documented scoring method exists (Phase 5), the pipeline's only honest verdict is
`insufficient_evidence`. A ranking by proposer confidence is included for transparency only.

## D-024 · 2026-11-01 · Specialists are data on one generic engine
The performance, infrastructure and wireless/service agents differ only in their cards
(config/catalogue/agents.yaml). Proposable hypotheses are derived from the catalogue. This
keeps every fault-specific fact in config and makes adding agents and faults code-free.
Connectivity is code because its analysis is graph reasoning, not metric detection.

## D-025 · 2026-11-01 · Three detection tests, not one
Pooled calibration bands were measured to be too wide at high noise: normal DNS success goes
down to about 46% and RSSI to about -86 dBm. The bands alone would miss most faults on clean
runs. We added (a) cited thresholds with a standard-error gate, and (b) an in-window change
test that uses the run's own noise and autocorrelation. Thresholds come from training-seed
sweeps (config rationale). **Leakage note:** the *decision* to add the standard-error gate to
cited thresholds was prompted by a false-positive count measured on held-out normal runs
(seeds 3-4). No value was fitted on them, but they are not perfectly clean. **Open (Q-005):**
Phase 8 should also report on fresh seeds never seen during development.

## D-026 · 2026-11-01 · AR(1)-corrected standard errors
Found by test: noise-free normal runs (pure AR(1) baseline) produced spurious CPU changes,
because an i.i.d. SE understates autocorrelated noise. Each segment's SE is now inflated by
sqrt((1+rho)/(1-rho)) with rho = lag-1 autocorrelation, capped at 0.9.

## D-027 · 2026-11-01 · No self-confirming localisation
Connectivity supports a hypothesis only when symptoms at two or more distinct locations fall
inside its blast radius. Found in a normal run, where a lone CPU blip was "100% inside" its
own device's radius.

## D-028 · 2026-11-01 · Negative evidence is posted
Non-significant clues are posted. Without them, `expect: normal` signature elements (e.g.
"transport healthy" for DNS failure, "no interface errors" for congestion) could never be
assessed, and contradictions would be impossible.

## D-029 · 2026-11-01 · Correlation by learned likelihood ratios (option c)
A naive-Bayes evidence model over recomputed signature statuses, with Laplace smoothing and
empirical-Bayes shrinkage toward pooled (role, expect) rates, followed by Platt scaling, all
fitted by `netcoop fit` on training seeds. Rejected: (a) hand-weighted log-odds (weights would
be guesses); (b) Dempster-Shafer (harder to calibrate and to explain per element).

## D-030 · 2026-11-01 · The correlator recomputes, it does not vote
Proposers' local confidences and specialists' own-clue stances are ignored: their evidence is
re-assessed from the clues themselves, each source observation counted once. Only *analytic*
stances (justified by others' clues, i.e. topology localisation) enter as an extra feature.
This makes corroboration count once per independent measurement, not once per agent that
repeats it.

## D-031 · 2026-11-01 · Rank and separate on calibrated log-odds
Found in the first full fit: calibrated probabilities saturate at about 1.0, so ranking by
probability fell back to alphabetical tie-breaking, and a probability margin could not tell
two strong candidates apart. Ranking and the near-tie margin now use calibrated log-odds.

## D-032 · 2026-11-01 · 'No fault' needs assessed evidence
`no_fault_detected` requires that, for every fault type with a possible root in the data,
some agent posted clues on at least one metric of every required group. Found by test: with
no specialists running, the system claimed 'no fault' because the metrics were merely
present in the input. Data nobody analysed cannot rule a fault out.

## D-033 · 2026-11-01 · Fitted margin is 0; near ties do not occur at this operating point
At a 90% target precision the grid search picks margin 0: breaking ties by log-odds never
cost precision on training. On held-out seeds no run had two candidates above the accept
threshold. **Consequence for Phase 6:** the courtroom has no natural work on this data, so it
must be exercised on deliberately ambiguous generated cases (e.g. evidence removed by the
mutator, or competing faults), and its value measured there.

## D-034 · 2026-11-01 · Courtroom trigger includes under-trained contenders
No natural near ties exist at the fitted operating point (D-033), but the learned model is
blind to fault types it never saw true. Measured on fresh seeds: genuine hardware failures
were reported as interface faults at confidence 1.0 in 32 of 40 cases. The courtroom therefore
also opens when a plausible, related, overlapping contender (or the top candidate) is of a type
with fewer than `trigger.min_training_positives` true training examples.

## D-035 · 2026-11-01 · 'Rising' is tested on the recent window
Mann-Kendall over the whole series reads a step (a failed device's error level that jumped
and stayed flat) as a trend. The catalogue's 'rising' means *still rising now*, which is what
separates a degrading interface from a dead device. Trends are now tested on the recent
window like the level tests. The correlation model was refitted (held-out precision
unchanged at 98.9%).

## D-036 · 2026-11-01 · Win margin on the quality-weighted scale
The first margin (an unweighted 2.0, i.e. one perfect required element) deferred every case
with any missing data, because quality-weighted points of a decisive confirmation came to
about 1.86. Measured: 39 of 72 held-out interface faults deferred. The margin is now 2 × 0.873,
where 0.873 is the 10th percentile of evidence quality of true training candidates; 16 of 72
now defer, all lacking the discriminating trend.

## D-037 · 2026-11-01 · The courtroom confirms or defers; it does not overrule into a claim
A courtroom win for the contender becomes the verdict only if the calibrated model also
accepts it. The courtroom's rubric is not calibrated, so turning its preference alone into a
claim would break the 'confidence from a calibrated method' requirement. The honest result
is insufficient evidence, with both hypotheses and the transcript reported.

## D-038 · 2026-11-01 · Ambiguity suite outside the main sweep
hardware_failure and device_overload injection was added to the stand-in generator but kept
out of the main sweep and the fit (config `ambiguity_suite`, fresh seeds 100-109). The suite
thus measures behaviour on faults the learned model never saw, and the new seeds give a
clean, never-touched evaluation set (partly addresses Q-005).

## D-039 · 2026-11-01 · Report confidence means confidence in what is asserted
The first rendering of a courtroom deferral read "Confidence: 1.00 (low)": the correlator's
confidence in an explanation the courtroom had rejected. A7 `confidence` is now the
calibrated confidence in the asserted outcome (root cause or 'no fault'), and 0.0 with
category `none` when nothing is asserted. The contenders' calibrated confidences stay
visible under `x_netcoop.alternatives_scored`.

## D-040 · 2026-11-01 · Evidence comes from the recomputed signature
Supporting evidence is taken from the correlator's independence-aware recomputation of the
reported candidate's signature, not from the proposer's own supporting-clue list. The report
therefore shows exactly the evidence the decision rested on, including other agents'
corroboration and 'stayed normal' evidence.

## D-041 · 2026-11-01 · Remediation is simulated only
`simulated_remediation` lists, per action, the effects expected if the diagnosis is right
(the metric returning to its cited baseline or threshold). Nothing is executed (`applied:
false`), per the brief's rule against touching campus infrastructure.

## Open questions
- **Q-001** ~~Sweep sizes~~ resolved by D-005.
- **Q-002** Canonical schema: derive from `docs/DATA_PROFILE.md` (Phase 1). Re-check if the
  organiser generator is later provided.
- **Q-004** Local-confidence weights (2/1) and connectivity fractions (0.6/0.3) are
  engineering choices; Phase 5 fitting may replace them.
- **Q-003** Ask the organisers whether their generator will be released; if so, re-run
  `make generate && make profile` and diff the profile against the current one.
