# Evaluation results

Measured on **1,080 fresh test runs**, using seeds never used for calibration, fitting or
development.

| metric | value |
|---|---|
| precision of claims (diagnoses + "no fault") | **98.6%** (12 wrong of 846) |
| root-cause accuracy over all runs | 77.2% |
| honest abstentions | 21.7% |
| macro-F1 | 0.860 |
| root localisation of correct-type claims | 100% |
| wrong claims on fault types never seen in training (120 runs) | 0 |

| file | contents |
|---|---|
| [EVALUATION.md](EVALUATION.md) | full results: per root cause, confusion matrix, robustness by noise, missing data, intensity and stacked format mutations, ablations |
| [CALIBRATION.md](CALIBRATION.md) | calibration quality and operating points of the correlation model |
| [COURTROOM_RESULTS.md](COURTROOM_RESULTS.md) | with versus without the courtroom on ambiguous cases (wrong claims 32 → 0) |
| [INTEROP_RESULTS.md](INTEROP_RESULTS.md) | the Translator against 22 kinds of format corruption (0 failures, 0 crashes) |
| [RUBRIC_MAP.md](RUBRIC_MAP.md) | each judging criterion mapped to its evidence |

To regenerate the results from the repository root, run `netcoop eval`; it takes about
7 minutes.
