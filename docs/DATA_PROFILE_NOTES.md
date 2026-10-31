## Notes (hand-written)

**Source.** Output of the provisional stand-in generator (`generator/synth.py`, D-004), 1080 runs,
profiled on an evenly spaced subset. Replace with the organiser's generator when available and
re-run `netcoop profile`; the canonical schema must follow whatever that profile shows.

**Two dialects are present and must both map to one canonical schema (Phase 1/2 input):**

| Concept | `netcoop_synth_v2` (JSONL) | `legacy_v1` (CSV) | Conversion |
|---|---|---|---|
| timestamp | `ts` ISO-8601 UTC | `time` epoch seconds | parse / `fromtimestamp(utc)` |
| schema version | `schema_version` "2.0" | `schema_ver` 1.0 (parsed as float) | normalise to string |
| record kind | `kind` field in one file | one file per kind | file name -> kind |
| link identity | `link_id` = `"<a>--<b>"` | `src`, `dst` endpoint pair | resolve via topology |
| hop latency / jitter | `latency_ms`, `jitter_ms` | `latency_us`, `jitter_us` | us / 1000 |
| loss | `loss_pct` (0-100) | `loss_ratio` (0-1) | x 100 |
| utilization | `utilization_pct` (0-100) | `util_ratio` (0-1) | x 100 |
| throughput | `throughput_mbps` | `tput_kbps` | / 1000 |
| device id | `device_id` | `hostname` | rename |
| device status | `status` up/degraded/down | `state` UP/DEGRADED/DOWN | lower-case |
| CPU / memory | `cpu_pct`, `mem_pct` (0-100) | `cpu_load`, `mem_used_ratio` (0-1) | x 100 |
| egress queue drops | `egress_queue_drops` (count/interval) | `q_drops` | rename |
| interface errors | `if_in_errors`, `if_out_errors` | `rx_errs`, `tx_errs` | rename |
| AP id | `ap_id` | `ap` | rename |
| RSSI / SNR | `rssi_dbm`, `snr_db` | `signal`, `snr` (unit implicit) | rename; unit inferred by plausibility |
| retransmissions | `retrans_pct` | `retry_ratio` | x 100 |
| associated clients | `clients` | `stations` | rename |
| service probe | `service` dns/dhcp, `vantage_id`, `server_id` | `svc` DNS/DHCP, `vantage`, no server | lower-case; server via topology |
| probe success | `success_pct` | `ok_ratio` | x 100 |
| probe response | `response_ms` | `resp_time_s` | x 1000 |
| topology | `topology.json` nodes (id,type,tier,zone,parent) + links (id,a,b,capacity_mbps) | `topology_edges.csv` parent, child, child_type (RTR/SW/AP/SRV), uplink_kbps | build graph; kbps / 1000 |

**Observations that matter for later phases**
- `loss_pct` is shared by `link` and `wireless` records in v2; it must be disambiguated by entity type.
- Legacy CSV values are rounded to 3 decimals, so ratios lose resolution (e.g. healthy link
  `loss_ratio` reads 0.0). The Translator should record this precision loss in provenance.
- Legacy topology has no tier/zone; the Connectivity agent must not rely on them.
- Missing data shows up as whole dropped records and as individual empty fields; integer counters
  become floats when a column contains nulls.
- Counter semantics: queue drops and interface errors are per-interval deltas, not cumulative counters.
