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
