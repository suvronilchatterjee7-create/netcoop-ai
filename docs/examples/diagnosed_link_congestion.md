# Incident inc-3735f38ffa49

**Status:** Diagnosed  
**Root cause:** link_congestion at lecture_hall-dist-01--lecture_hall-acc-02: Traffic on a link exceeds what it can forward without queueing and loss.  
**Confidence:** 1.00 (high)

## Affected

`lecture_hall-dist-01--lecture_hall-acc-02`, `lecture_hall-dist-01`, `dhcp`, `dns`, `lecture_hall-acc-02-ap-01`, `lecture_hall-acc-02`

## Evidence

| # | metric | value | interpretation | agent |
|---|---|---|---|---|
| 1 | utilization | 91.46 | utilization on lecture_hall-dist-01--lecture_hall-acc-02: recent median 91.5 percent is above the normal-operation baseline of 27.4 percent by 5.29 robust standard deviations, abnormal in 91% of recent samples; data quality 0.93 [baselines.utilization.link] | performance |
| 2 | packet_loss | 1.869 | packet_loss on lecture_hall-dist-01--lecture_hall-acc-02: recent median 1.87 percent is above the normal-operation baseline of 0.02 percent by 50 robust standard deviations, abnormal in 100% of recent samples; data quality 0.94 [baselines.packet_loss.link] | performance |
| 3 | jitter | 8.211 | jitter on lecture_hall-dist-01--lecture_hall-acc-02: recent median 8.21 ms is above the normal-operation baseline of 0.197 ms by 50 robust standard deviations, abnormal in 100% of recent samples; data quality 0.96 [baselines.jitter.link] | performance |
| 4 | latency | 26.78 | latency on lecture_hall-dist-01--lecture_hall-acc-02: recent median 26.8 ms is above the normal-operation baseline of 0.792 ms by 50 robust standard deviations, abnormal in 100% of recent samples; data quality 0.95 [baselines.latency.link] | performance |
| 5 | egress_queue_drops | 97 | egress_queue_drops on lecture_hall-dist-01: recent median 97 count is above the normal-operation baseline of 0 count by 50 robust standard deviations, abnormal in 100% of recent samples; data quality 0.96 [baselines.egress_queue_drops.switch] | infrastructure |
| 6 | service_response_time | 38.41 | service_response_time on dhcp (probed from lecture_hall-acc-02-ap-01): recent median 38.4 ms is above the normal-operation baseline of 7.89 ms by 11 robust standard deviations, abnormal in 100% of recent samples; data quality 0.94 [baselines.service_response_time.service] | wireless_service |
| 7 | interface_in_errors | 0 | interface_in_errors on lecture_hall-dist-01 stayed normal: recent median 0 count vs normal-operation baseline 0 count, as link_congestion predicts; data quality 0.96 [baselines.interface_in_errors.switch] | infrastructure |
| 8 | service_response_time | 38.4 | service_response_time on dns (probed from lecture_hall-acc-02): recent median 38.4 ms is above the normal-operation baseline of 7.89 ms by 11 robust standard deviations, abnormal in 100% of recent samples; data quality 0.99 [baselines.service_response_time.service] | wireless_service |

## Why (log-odds of the reported candidate)

| component | status | contribution |
|---|---|---|
| prior (link_congestion) | 94 true / 26 false training candidates | +1.11 |
| utilization deviates above @ root (required) | satisfied | +0.16 |
| egress_queue_drops deviates above @ root_upstream (supporting) | satisfied | +1.95 |
| latency deviates above @ root (supporting) | satisfied | +1.95 |
| jitter deviates above @ root (supporting) | satisfied | +1.95 |
| packet_loss deviates above @ root (supporting) | satisfied | +1.81 |
| service_response_time deviates above @ probes_downstream (supporting) | satisfied | +1.22 |
| interface_in_errors normal above @ root_endpoints (supporting) | satisfied | +0.03 |
| analytic stance (topology) | support | +2.24 |
| evidence quality | bin 1 (quality 0.95) | +0.03 |

## Recommended actions (for human review)

1. Identify the top traffic sources on lecture_hall-dist-01--lecture_hall-acc-02 and rate-limit or reschedule bulk transfers.
   - *Simulated (not applied):* expect utilization on lecture_hall-dist-01--lecture_hall-acc-02 returns from 91.5 to about 27.4 percent (baseline); packet_loss on lecture_hall-dist-01--lecture_hall-acc-02 returns from 1.87 to about 0.02 percent (baseline); jitter on lecture_hall-dist-01--lecture_hall-acc-02 returns from 8.21 to about 0.197 ms (baseline); latency on lecture_hall-dist-01--lecture_hall-acc-02 returns from 26.8 to about 0.792 ms (baseline); egress_queue_drops on lecture_hall-dist-01 returns from 97 to about 0 count (baseline); service_response_time on dhcp (from lecture_hall-acc-02-ap-01) returns from 38.4 to about 7.89 ms (baseline); service_response_time on dns (from lecture_hall-acc-02) returns from 38.4 to about 7.89 ms (baseline)
2. Apply or review QoS so interactive traffic is prioritised on lecture_hall-dist-01--lecture_hall-acc-02.
   - *Simulated (not applied):* expect utilization on lecture_hall-dist-01--lecture_hall-acc-02 returns from 91.5 to about 27.4 percent (baseline); packet_loss on lecture_hall-dist-01--lecture_hall-acc-02 returns from 1.87 to about 0.02 percent (baseline); jitter on lecture_hall-dist-01--lecture_hall-acc-02 returns from 8.21 to about 0.197 ms (baseline); latency on lecture_hall-dist-01--lecture_hall-acc-02 returns from 26.8 to about 0.792 ms (baseline); egress_queue_drops on lecture_hall-dist-01 returns from 97 to about 0 count (baseline); service_response_time on dhcp (from lecture_hall-acc-02-ap-01) returns from 38.4 to about 7.89 ms (baseline); service_response_time on dns (from lecture_hall-acc-02) returns from 38.4 to about 7.89 ms (baseline)
3. If sustained, plan a capacity upgrade or add a parallel uplink for lecture_hall-dist-01--lecture_hall-acc-02.
   - *Simulated (not applied):* expect utilization on lecture_hall-dist-01--lecture_hall-acc-02 returns from 91.5 to about 27.4 percent (baseline); packet_loss on lecture_hall-dist-01--lecture_hall-acc-02 returns from 1.87 to about 0.02 percent (baseline); jitter on lecture_hall-dist-01--lecture_hall-acc-02 returns from 8.21 to about 0.197 ms (baseline); latency on lecture_hall-dist-01--lecture_hall-acc-02 returns from 26.8 to about 0.792 ms (baseline); egress_queue_drops on lecture_hall-dist-01 returns from 97 to about 0 count (baseline); service_response_time on dhcp (from lecture_hall-acc-02-ap-01) returns from 38.4 to about 7.89 ms (baseline); service_response_time on dns (from lecture_hall-acc-02) returns from 38.4 to about 7.89 ms (baseline)

## Data quality

Overall 0.96. Affected entities: `dhcp` 0.96, `dns` 0.96, `lecture_hall-acc-02` 0.97, `lecture_hall-acc-02-ap-01` 0.96, `lecture_hall-dist-01` 0.97, `lecture_hall-dist-01--lecture_hall-acc-02` 0.94.

## Provenance

Evidence from: performance, infrastructure, wireless_service, correlator, connectivity.
Input `3735f38ffa49`, config `010e1f4c337a`, code 0.1.0+5b6f1f6, protocol 2.0, vocabulary 1.0, seed 20261031.
