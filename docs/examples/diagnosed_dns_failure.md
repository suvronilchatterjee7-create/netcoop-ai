# Incident inc-cc9c4f34c27d

**Status:** Diagnosed  
**Root cause:** dhcp_service_failure at dhcp: DHCP fails or is slow while the transport network is healthy.  
**Confidence:** 1.00 (high)

## Affected

`dhcp`, `lecture_hall-acc-02`, `hostel-acc-03-ap-01`, `hostel-acc-03-ap-03`, `lecture_hall-acc-01-ap-03`, `department-acc-03-ap-01`, `department-acc-01-ap-02`

## Evidence

| # | metric | value | interpretation | agent |
|---|---|---|---|---|
| 1 | service_success_rate | 33.24 | service_success_rate on dhcp (probed from lecture_hall-acc-02): recent median 33.2 percent is below the normal-operation baseline of 99.5 percent by 3.17 robust standard deviations, abnormal in 100% of recent samples; data quality 1.00 [baselines.service_success_rate.service] | wireless_service |
| 2 | service_response_time | 410.4 | service_response_time on dhcp (probed from hostel-acc-03-ap-01): recent median 410 ms is above the normal-operation baseline of 7.89 ms by 50 robust standard deviations, abnormal in 100% of recent samples; data quality 1.00 [baselines.service_response_time.service] | wireless_service |
| 3 | packet_loss | 0.015 | packet_loss on department-acc-03--department-acc-03-ap-01 stayed normal: recent median 0.015 percent vs normal-operation baseline 0.02 percent, as dhcp_service_failure predicts; data quality 1.00 [baselines.packet_loss.link] | performance |
| 4 | latency | 0.646 | latency on department-acc-01--department-acc-01-ap-01 stayed normal: recent median 0.646 ms vs normal-operation baseline 0.792 ms, as dhcp_service_failure predicts; data quality 1.00 [baselines.latency.link] | performance |
| 5 | service_success_rate | 33.28 | service_success_rate on dhcp (probed from hostel-acc-03-ap-03): recent median 33.3 percent is below the normal-operation baseline of 99.5 percent by 3.17 robust standard deviations, abnormal in 100% of recent samples; data quality 1.00 [baselines.service_success_rate.service] | wireless_service |
| 6 | service_response_time | 417.8 | service_response_time on dhcp (probed from lecture_hall-acc-01-ap-03): recent median 418 ms is above the normal-operation baseline of 7.89 ms by 50 robust standard deviations, abnormal in 100% of recent samples; data quality 1.00 [baselines.service_response_time.service] | wireless_service |
| 7 | service_success_rate | 33.48 | service_success_rate on dhcp (probed from department-acc-03-ap-01): recent median 33.5 percent is below the normal-operation baseline of 99.5 percent by 3.16 robust standard deviations, abnormal in 100% of recent samples; data quality 1.00 [baselines.service_success_rate.service] | wireless_service |
| 8 | service_response_time | 400.6 | service_response_time on dhcp (probed from department-acc-01-ap-02): recent median 401 ms is above the normal-operation baseline of 7.89 ms by 50 robust standard deviations, abnormal in 100% of recent samples; data quality 1.00 [baselines.service_response_time.service] | wireless_service |

## Why (log-odds of the reported candidate)

| component | status | contribution |
|---|---|---|
| prior (dhcp_service_failure) | 55 true / 0 false training candidates | +2.04 |
| service_success_rate deviates below @ probes_of_root (required) | satisfied | +0.54 |
| service_response_time deviates above @ probes_of_root (supporting) | satisfied | +1.11 |
| packet_loss normal above @ probe_paths (supporting) | satisfied | -0.00 |
| latency normal above @ probe_paths (supporting) | satisfied | -0.06 |
| analytic stance (topology) | support | +2.24 |
| evidence quality | bin 2 (quality 1.00) | +0.03 |

## Recommended actions (for human review)

1. Check the DHCP server process, scope utilisation (address pool exhaustion) and relay configuration.
   - *Simulated (not applied):* expect service_success_rate on dhcp (from lecture_hall-acc-02) returns from 33.2 to about 99.5 percent (baseline); service_response_time on dhcp (from hostel-acc-03-ap-01) returns from 410 to about 7.89 ms (baseline); service_success_rate on dhcp (from hostel-acc-03-ap-03) returns from 33.3 to about 99.5 percent (baseline); service_response_time on dhcp (from lecture_hall-acc-01-ap-03) returns from 418 to about 7.89 ms (baseline); service_success_rate on dhcp (from department-acc-03-ap-01) returns from 33.5 to about 99.5 percent (baseline); service_response_time on dhcp (from department-acc-01-ap-02) returns from 401 to about 7.89 ms (baseline)
2. Fail over to the standby DHCP server; verify helper/relay addresses on the access layer.
   - *Simulated (not applied):* expect service_success_rate on dhcp (from lecture_hall-acc-02) returns from 33.2 to about 99.5 percent (baseline); service_response_time on dhcp (from hostel-acc-03-ap-01) returns from 410 to about 7.89 ms (baseline); service_success_rate on dhcp (from hostel-acc-03-ap-03) returns from 33.3 to about 99.5 percent (baseline); service_response_time on dhcp (from lecture_hall-acc-01-ap-03) returns from 418 to about 7.89 ms (baseline); service_success_rate on dhcp (from department-acc-03-ap-01) returns from 33.5 to about 99.5 percent (baseline); service_response_time on dhcp (from department-acc-01-ap-02) returns from 401 to about 7.89 ms (baseline)

## Data quality

Overall 1.00. Affected entities: `department-acc-01-ap-02` 1.00, `department-acc-03-ap-01` 1.00, `dhcp` 1.00, `hostel-acc-03-ap-01` 1.00, `hostel-acc-03-ap-03` 1.00, `lecture_hall-acc-01-ap-03` 1.00, `lecture_hall-acc-02` 1.00.

## Provenance

Evidence from: wireless_service, performance, correlator, connectivity.
Input `cc9c4f34c27d`, config `010e1f4c337a`, code 0.1.0+5b6f1f6, protocol 2.0, vocabulary 1.0, seed 20261031.
