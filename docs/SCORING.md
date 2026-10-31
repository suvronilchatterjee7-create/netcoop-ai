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
| trend (counters) | Mann-Kendall z, Theil-Sen slope | p < `trend.alpha`, slope > 0, at least `trend.min_samples` | - | there is strong serial correlation (inflates the false-positive rate) |
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
