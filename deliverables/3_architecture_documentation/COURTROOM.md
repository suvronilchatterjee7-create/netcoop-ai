# Courtroom tie-break

```bash
netcoop courtroom-eval      # ablation with vs without the courtroom -> docs/COURTROOM_RESULTS.md
```

## Why it exists here

The correlator (SCORING.md §4) learns its evidence weights from labelled training data. That
is its strength and also its blind spot. Phase 5 found no natural near ties: the learned
model separates candidates by at least 5 log-odds. But two catalogue faults,
`hardware_failure` and `device_overload`, are **never injected** by the main generator sweep.
Their learned weights therefore encode "this never happens", not evidence. On genuine
hardware failures the correlator alone was **confidently wrong**: it reported
`interface_fault` at confidence 1.0 in 32 of 40 fresh cases (COURTROOM_RESULTS.md).

The courtroom is opened when the correlator's decision cannot be trusted to rest on
evidence:

1. **Near tie:** the calibrated log-odds gap between the two best live candidates is below
   the fitted margin.
2. **Under-trained contender:** a live competing candidate, or the top candidate itself, is
   of a fault type with fewer than `trigger.min_training_positives` true training examples.
   To count, it must also:
   - satisfy every required signature group
   - be related to the top candidate in the catalogue (`competes_with` or `explains`)
   - overlap it in location (one root inside the other's blast radius)

## Procedure (deterministic, rule-based)

| step | who | what |
|---|---|---|
| opening | correlator | posts a preliminary VERDICT and the case: the top candidate A against contender B, with the reason |
| discovery | prosecutor (for A), defense (for B) | REQUEST, by capability, every metric of their own signature that has no evidence in scope yet. Specialists answer in up to `judge.max_rounds` rounds |
| briefs | prosecutor, defense | score their own case on **discriminating evidence** (below) |
| arguments | prosecutor, defense | SUPPORT their own hypothesis (citing confirming clues) and CONTRADICT the other's (citing its failed predictions), with point totals in the note |
| ruling | judge | final VERDICT (causation: the preliminary VERDICT) with both briefs and the ruling in its rationale |

### Discriminating evidence (the rubric)

- **Differential scope:** each signature element of a side is assessed only on its
  *differential* scope, the part of its scope where the other side does not predict the same
  thing (same metric, statistic kind and expectation). Shared predictions cannot separate two
  explanations, so they score nothing.
- **Same semantics as the signature:** the any / quorum rules apply, and required groups are
  alternatives.
- **Independence:** each observation counts once per side.

| point | value |
|---|---|
| element confirmed on its differential scope | + weight (required 2, supporting 1) × mean data quality of its clues |
| element failed on its differential scope | − the same. A failed member of a required group is charged once, and only if the group is not satisfied elsewhere, including by a shared member |
| `expect: normal` element | counts only where the other side predicts a deviation (a conflicting prediction) |
| required element with no evidence at all | − `rubric.missing_required` |
| explained away: the other side's catalogue entry `explains` this type at this location, and this side has no positive points | − `rubric.explained_away` |

### Ruling

A side wins with a lead of at least `judge.win_margin`: one required discriminating
confirmation at the evidence quality of typical correct diagnoses. Then:

- **The top candidate wins:** it is **confirmed**, keeping its calibrated confidence.
- **The contender wins:** it becomes the verdict only if the calibrated model also accepts it
  (confidence ≥ accept). Otherwise the court **defers**: the courtroom never turns an
  uncalibrated preference into a claim.
- **No clear lead:** the court **defers**. The result is `insufficient_evidence`, both
  hypotheses are reported, and the missing evidence names "evidence that discriminates A
  from B".

The report's `x_netcoop.courtroom` block carries:

- the contenders
- the number of rounds
- the outcome: resolved or deferred
- a summary of both briefs and the ruling
- every transcript message id

## Worked example: interface fault vs hardware failure

| truth | discriminating evidence | ruling |
|---|---|---|
| interface fault on an access uplink | errors **still rising** at the downstream end (only an interface fault predicts a rising trend: +2 × q); the hardware failure's predicted loss on the device's *other* links did not happen (−1 × q) | confirmed |
| interface fault on an AP link | rising errors (+2 × q); the AP has no other links, so the hardware failure has nothing exclusive | confirmed |
| hardware failure of an access switch | errors stepped up and stayed flat, so no rising trend (the interface fault's group is satisfied only by shared evidence); loss on *all* attached links (+1 × q for the hardware failure); the interface fault is explained away by the hardware failure (−2) | evidence favours the hardware failure, but the model gives it ≈0.45 < accept: **deferred** |
| hardware failure of an AP | nothing exclusive for either side, and the interface fault is explained away | deferred |

## Measured effect (COURTROOM_RESULTS.md)

| suite | wrong claims without → with courtroom | correct claims without → with |
|---|---|---|
| ambiguity suite (120 runs, fresh seeds 100–109) | **32 → 0** | 80 → 80 |
| held-out main suite (432 runs) | 4 → 4 (pre-existing weak-Wi-Fi misses; courtroom not involved) | 351 → 331 |

On the held-out suite, 20 interface faults move from correct to abstained. In those runs,
heavy missing data or low intensity hides the rising-error trend, which is the only evidence
that separates a failing interface from a failing device. The model was right on them, but
only by virtue of a prior that cannot be trusted on real networks, so deferring is the
honest call.

## Limitations

- The rubric is the catalogue's predictions plus simple accounting. It weighs evidence
  *kinds* by role, not by how surprising each deviation is.
- With no courtroom-ready training labels for unseen faults, a contender's win can only
  defer, never diagnose, unless the calibrated model agrees. Fitting on labelled
  hardware-failure data (e.g. the organiser generator, if it injects such faults) would let
  the courtroom resolve these cases instead of deferring.
- Near ties proper (gap < fitted margin) do not occur at the current operating point
  (D-033). The mechanism is covered by unit tests of the decision policy.
