# Incident inc-1a0677de2579

**Status:** Insufficient evidence  
**Root cause:** insufficient evidence to name a root cause; best explanations: interface_fault at core-rtr-01--hostel-dist-01 or hardware_failure at hostel-dist-01  
**Confidence:** 0.00 (none)

## Affected

`core-rtr-01--hostel-dist-01`, `hostel-dist-01`

## Evidence

| # | metric | value | interpretation | agent |
|---|---|---|---|---|
| 1 | device_status | 1 | device_status on hostel-dist-01 was in an abnormal state in 100% of recent samples; data quality 0.96 [baselines.device_status.switch] | infrastructure |
| 2 | packet_loss | 97.35 | packet_loss on hostel-dist-01--hostel-acc-02: recent median 97.4 percent is above the normal-operation baseline of 0.02 percent by 50 robust standard deviations, abnormal in 100% of recent samples; data quality 0.96 [baselines.packet_loss.link] | performance |
| 3 | packet_loss | 98.51 | packet_loss on core-rtr-01--hostel-dist-01: recent median 98.5 percent is above the normal-operation baseline of 0.02 percent by 50 robust standard deviations, abnormal in 100% of recent samples; data quality 0.96 [baselines.packet_loss.link] | performance |
| 4 | interface_in_errors | 4 | interface_in_errors on hostel-dist-01: recent median 4 count is above the normal-operation baseline of 0 count by 5.15 robust standard deviations, abnormal in 83% of recent samples; data quality 0.94 [baselines.interface_in_errors.switch] | infrastructure |
| 5 | utilization | 0 | utilization on core-rtr-01--hostel-dist-01 stayed normal: recent median 0 percent vs normal-operation baseline 27.4 percent, as interface_fault predicts; data quality 0.98 [baselines.utilization.link] | performance |
| 6 | packet_loss | 100 | packet_loss on hostel-dist-01--hostel-acc-01: recent median 100 percent is above the normal-operation baseline of 0.02 percent by 50 robust standard deviations, abnormal in 100% of recent samples; data quality 0.96 [baselines.packet_loss.link] | performance |

## Why (log-odds of the reported candidate)

| component | status | contribution |
|---|---|---|
| prior (interface_fault) | 134 true / 122 false training candidates | +0.11 |
| interface_in_errors deviates rising @ root_endpoints (required) | violated | -0.08 |
| interface_in_errors deviates above @ root_endpoints (required) | unknown | -0.08 |
| interface_out_errors deviates above @ root_endpoints (required) | violated | +0.00 |
| packet_loss deviates above @ root (supporting) | satisfied | +2.93 |
| device_status deviates changed @ root_downstream (supporting) | satisfied | +3.08 |
| utilization normal above @ root (supporting) | satisfied | -0.01 |
| analytic stance (topology) | support | +2.24 |
| evidence quality | bin 1 (quality 0.96) | +0.03 |

## Alternative explanations

- interface_fault at core-rtr-01--hostel-dist-01 (confidence 1.00)
- hardware_failure at hostel-dist-01 (confidence 0.03)

## Courtroom

Contenders: interface_fault@core-rtr-01--hostel-dist-01 vs hardware_failure@hostel-dist-01. Outcome: **deferred** after 1 round(s); 2 transcript messages.

- prosecutor for interface_fault@core-rtr-01--hostel-dist-01: -2.00 (explained_away -2.00)
- defense for hardware_failure@hostel-dist-01: +0.96 (confirmed +0.96)
- evidence favours hardware_failure@hostel-dist-01, but the calibrated model gives it 0.03 < 0.98 (never trained on it): deferred

## Recommended actions (for human review)

1. Collect: evidence that discriminates interface_fault@core-rtr-01--hostel-dist-01 from hardware_failure@hostel-dist-01
2. If interface_fault at core-rtr-01--hostel-dist-01 is confirmed: Check cabling, transceivers and port counters on both ends of core-rtr-01--hostel-dist-01 (core-rtr-01 / hostel-dist-01).
3. If hardware_failure at hostel-dist-01 is confirmed: Check power, environment and hardware logs of hostel-dist-01; run vendor diagnostics.

## Missing evidence

- evidence that discriminates interface_fault@core-rtr-01--hostel-dist-01 from hardware_failure@hostel-dist-01

## Limitations

- courtroom deferred: evidence favours hardware_failure@hostel-dist-01, but the calibrated model gives it 0.03 < 0.98 (never trained on it): deferred

## Data quality

Overall 0.96. Affected entities: `core-rtr-01--hostel-dist-01` 0.97, `hostel-dist-01` 0.95.

## Provenance

Evidence from: infrastructure, performance, correlator, prosecutor, defense, judge.
Input `1a0677de2579`, config `010e1f4c337a`, code 0.1.0+5b6f1f6, protocol 2.0, vocabulary 1.0, seed 20261031.
