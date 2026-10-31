# Scoring methods

Every formula that produces a number used in a decision is documented here: what it computes,
why it was chosen, what it assumes and how it fails. Parameters live in `config/*.yaml`.
Sections 2 onwards (anomaly detection, evidence correlation, calibration, the courtroom
rubric) are added in Phases 4–6.

## 1. Data quality (Translator)

Each OBSERVATION series gets four components in [0, 1]:

| component | definition |
|---|---|
| completeness | valid samples / distinct timestamps in the series' source(s) |
| freshness | 1 while the age of the last sample ≤ `stale_after_intervals` × interval, then `0.5 ^ ((age − stale_after) / half_life)` |
| plausibility | valid samples / (valid + rejected for type or range) |
| mapping_certainty | lowest certainty along the mapping path: exact 1.0, normalised name 0.95, unit from suffix 0.95, unit inferred 0.7, entity not in topology 0.6 (multiplied when two apply) |

**Combination:** `score = (Π cᵢ^wᵢ)^(1/Σwᵢ)`, a weighted geometric mean, with weights in
`config/translator.yaml` (currently equal).

- **Why geometric:** quality is multiplicative in effect. Data that is complete but
  implausible, or plausible but mapped by guesswork, should not average out to "fairly good".
  In a geometric mean any component near 0 drives the score towards 0, while an arithmetic
  mean would let good components hide a bad one.
- **Assumes:** the four components are roughly independent failure modes and equally
  important. Phase 5 may fit the weights on generated data.
- **Fails when:** a component is mis-estimated. For example, completeness assumes every source
  polls on one grid, so a source that legitimately polls less often looks incomplete. The
  ordinal certainty levels are judgement calls (D-013), and Phase 8 checks how sensitive
  accuracy is to them.

The reference time and interval used for freshness are robust medians (the median of each
source's newest timestamp, and the median sampling interval). One badly time-shifted source
therefore cannot make every other source look stale.

## 2. Anomaly detection (all specialists, `netcoop/detection.py`)

Each series of the recent window (`window.recent_fraction` of the series, at least
`window.min_samples` samples) is judged by up to three independent tests. The first that is
significant is reported. If none is significant, the calibrated comparison (or else the next
available one) is reported as **negative evidence**.

| test | statistic | significant when | adapts to | fails when |
|---|---|---|---|---|
| calibrated band | recent median; robust z = (median - mu0)/s0 with s0 = max(1.4826 MAD0, (band - mu0)/2.576) | at least `min_persistence` of recent samples beyond the `band_quantile` band of normal operation for that metric and device type (from `netcoop calibrate`), and the median beyond mu0 | device type | the calibration pool is noisier than the current data, which makes the band wide and costs sensitivity |
| cited threshold | recent median vs `thresholds.<metric>` (ITU-T G.114, WLAN design guides, ...) | a majority of recent samples beyond it, **and** the median beyond it by more than `threshold_test.min_standard_errors` SE of the median | nothing (absolute) | the threshold suits a different context (e.g. the end-to-end G.114 delay applied per hop) |
| in-window change | z = (median_recent - median_early) / sqrt(SE_r^2 + SE_e^2), SE = 1.2533 x 1.4826 MAD / sqrt(n) x sqrt((1+rho)/(1-rho)) | z >= `change.min_z` **and** a majority of recent samples beyond the earlier extreme | the current run's own noise level and autocorrelation | the fault began before the window (no "before"), or there is a slow legitimate trend such as a diurnal cycle |
| trend (counters) | Mann-Kendall z, Theil-Sen slope **on the recent window** (D-035) | p < `trend.alpha`, slope > 0, at least `trend.min_samples` | - | there is strong serial correlation (inflates the false-positive rate) |
| enum state | share of recent samples in a non-healthy state | at least `min_persistence` and above the calibrated normal share | - | - |

- **Persistence** (a majority of recent samples) is what stops single spikes. With a 0.5%
  per-sample exceedance rate, a chance majority over 15 samples has binomial-tail
  probability below 1e-20.
- **Deviations** are capped at `max_deviation`, so one counter cannot dominate correlation.
- **`change.min_z`** was chosen by sweep on training seeds (see its rationale in config):
  false-positive rate of findings on normal runs 0.09%, with required-signature detection on
  fault targets at 79.6%.
- **Cited-threshold false alarms:** before the standard-error condition, the cited threshold
  produced 0.96% false-positive findings on held-out normal runs. With it, 0.07%.

## 3. Proposer confidence and stances

- **Local confidence** = (sum of weights of satisfied signature elements / sum of weights of
  the elements the agent could assess) x mean data quality of the clues used. The weights are
  `required` 2 and `supporting` 1. It deliberately ignores elements the agent cannot see:
  those are other agents' business, through stances.
- **Stance strength** (specialists) uses the same weight ratio, restricted to satisfied
  (SUPPORT) or violated (CONTRADICT) elements.
- **Connectivity strength** is the share of symptomatic locations inside the blast radius
  (SUPPORT), or outside it (CONTRADICT). The thresholds are in `config/specialist.yaml`.
- **Assumes:** catalogue signatures are complete enough that satisfied/assessed is a fair
  summary.
- **Fails when:** an agent can assess only supporting elements, so its ratio rests on weak
  evidence. That is why the correlator (Phase 5) recomputes support from all clues and does
  not trust local confidences.

## 4. Fault correlation (`netcoop/correlation/`)

**Choice:** option (c) of the brief: naive-Bayes-style likelihood ratios learned from
generated data, followed by Platt calibration. Why this over a hand-weighted log-odds sum or
Dempster-Shafer:

- **Data-derived:** every weight is estimated from labelled training candidates, so no
  evidence weight is a guess.
- **Explainable:** a candidate's score is a sum of per-element log-likelihood ratios, which
  the report can itemise ("utilisation satisfied: +2.1").
- **Deterministic:** no iterative fusion whose result depends on order.

### Candidates and features (`features.py`)

- **Candidates:** a candidate is a distinct (fault type, root) pair proposed by any agent.
  Several proposers of the same pair merge into one candidate.
- **Signature recomputation:** each catalogue element is re-assessed from **all agents'
  clues**. A proposer's local confidence is not used.
- **Independence:** elements are assessed required first. A source observation counted for
  one element is not used for another, so a level clue and a trend clue derived from the
  same series cannot both vote, and two agents citing one observation count once.
- **Analytic stance:** a SUPPORT or CONTRADICT justified only by clues its sender did *not*
  author (e.g. Connectivity's blast radius). It becomes the feature
  `analytic ∈ {support, contradict, none}`. Stances justified by the sender's own clues are
  ignored, because those clues are already in the signature.
- **Evidence quality:** the mean data quality of the clues used, in tertile bins.

### Score

```
score(c) = prior_logit[type] + Σ_e LLR[type][e][status_e] + LLR_analytic[analytic] + LLR_quality[bin]
LLR[s]   = log P(s | candidate true) − log P(s | candidate false)
P(s | y) = (n_s,y + k · P_pool(s | y, role, expect)) / (N_y + k)        (shrinkage, k = 20)
P_pool   = Laplace-smoothed rate over all elements with the same (role, expect)
confidence = sigmoid(a · score + b)                                      (Platt, fitted on training)
```

- **Corroboration:** independent elements satisfied by different agents add LLRs, so
  corroboration raises the score.
- **Contradiction:** a violated element, or an `expect: normal` element that deviates,
  contributes its (typically negative) violated-LLR, so contradiction lowers it.
- **Unknown evidence:** "unknown" has its own LLR. A missing agent or metric therefore moves
  the score only as much as missingness was informative in training.
- **Assumes:** conditional independence of element statuses given truth (the naive-Bayes
  assumption). This is partly enforced by the observation-level de-duplication above. Where
  it still fails (correlated symptoms), naive Bayes is over-confident, and Platt scaling
  corrects the over-confidence globally, not per fault.
- **Fails when:** a fault type has few training examples. Its rates then fall back to the
  pooled ones, so it is scored like a "generic" fault of its signature shape. This is the
  case for device_overload and hardware_failure, which the generator never injects.

### Causal precedence

Candidates are sorted by confidence. A candidate is merged into a more (or equally) confident
candidate whose catalogue entry `explains` its type and whose blast radius contains its root
(e.g. weak Wi-Fi at an AP below a congested link). A merged candidate stops competing and is
listed as explained.

### Decision policy (`model.decide`)

1. **Diagnosed:** the best live candidate's confidence ≥ `accept`, and its margin over the
   runner-up ≥ `margin`.
2. **Near tie:** confidence ≥ `accept` but the margin is too small. This is flagged
   `near_tie` and is `insufficient_evidence` until the Phase 6 courtroom adjudicates.
3. **Otherwise, no fault is claimed:**
   - **Unassessable faults:** if any fault type has possible roots in the data but none of
     its required metrics was observed, the system cannot rule it out, so the result is
     `insufficient_evidence` with that gap listed. Fault types with no possible root in the
     data (e.g. no access points) are noted as not applicable.
   - **No fault detected:** if P(normal | data-quality bin, number of significant clues),
     estimated on training runs left undiagnosed, is ≥ `normal_accept`, the result is
     `no_fault_detected`.
   - **Insufficient evidence:** otherwise, `insufficient_evidence`, listing the unknown
     signature elements of the top candidates as missing evidence.

`accept`, `margin` and `normal_accept` are chosen by grid search on the training seeds as the
most permissive values whose claims are at least `decision.target_precision` (90%) correct.
`accept` never goes below `decision.min_accept` (0.5).

**Confidence categories:**

- **high:** confidence ≥ the fitted accept (or no-fault) threshold, i.e. the operating point
  that met 90% precision in training
- **medium:** confidence ≥ 0.5
- **low:** below that

Calibration quality (Brier, ECE, reliability table) and the decision outcomes on held-out
seeds are in [CALIBRATION.md](CALIBRATION.md).

## 5. Courtroom rubric (`netcoop/courtroom/`)

The full procedure is in [COURTROOM.md](COURTROOM.md). In summary:

```
points(side) =  Σ_confirmed  w_role · q   −  Σ_failed  w_role · q      (differential scope only)
             −  missing_required · [required element without any evidence]
             −  explained_away   · [other side explains this type here and side has no positive points]
lead = points(prosecution) − points(defense);  clear win iff |lead| ≥ win_margin
```

- **Differential scope:** the part of an element's scope where the other hypothesis does not
  make the same prediction.
- **Assumes:** catalogue signatures state what each fault predicts *and where*, so the
  difference between two signatures is what discriminates them.
- **Fails when:** signatures are incomplete. A fault with an unlisted symptom gets no credit
  for it, and an unlisted shared symptom may look discriminating.
- **Why `win_margin` is quality-weighted:** points are multiplied by data quality, so the
  margin is expressed at the evidence quality of typical correct training diagnoses (D-036).
