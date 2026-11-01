# Specialist agents and the hypothesis catalogue

```bash
netcoop calibrate                         # derive normal baselines from training-seed normal runs
netcoop run data/generated/weak_wifi/<run> -v
```

## The agents

| agent | defined in | evidence | can propose |
|---|---|---|---|
| `performance` | `config/catalogue/agents.yaml` | latency, jitter, packet loss, throughput, utilisation (links) | link_congestion |
| `infrastructure` | `config/catalogue/agents.yaml` | device status, CPU, memory, egress queue drops, interface errors and their trends | interface_fault, hardware_failure, device_overload |
| `wireless_service` (optional) | `config/catalogue/agents.yaml` | RSSI, SNR, retransmissions, wireless loss, clients, DNS/DHCP probe success and response time | weak_wifi_signal, dns_service_failure, dhcp_service_failure |
| `connectivity` | `netcoop/agents/connectivity.py` | topology: blast radius, lowest common upstream, localised vs widespread | (judges localisation of every hypothesis) |

The three metric specialists are **data**: each is a card (id, description, metrics,
optional) running the generic engine in `netcoop/agents/specialist.py`. The hypotheses an
agent may propose are not listed by hand. They are derived from the catalogue: an agent may
propose a fault if it can observe at least one element of every *required* signature group.
Adding an agent means adding a card; adding a fault means adding a catalogue entry. Neither
needs an engine change.

## What a specialist does each round

1. **Clues.** Every observation of its metrics goes through the detection library
   (SCORING.md §2) and becomes a CLUE. The clue carries the statistic, value, unit, the
   baseline or threshold it was compared with (with its config key), the direction, the
   normalised deviation, the persistence, the window, the source observation id and the data
   quality. Non-significant clues are posted too, as explicit negative evidence ("checked,
   normal"). Counter metrics also get a trend clue (Mann-Kendall / Theil-Sen).
2. **Hypotheses.**
   - **Candidates:** candidate roots are found by inverting the scope of each significant
     clue that matches a required signature element. For example, errors on device D, under
     scope `root_endpoints`, point to every link touching D.
   - **Admission:** a candidate is admitted if its type matches the hypothesis' locus, and is
     proposed when every required group the agent can assess is satisfied.
   - **Content:** the hypothesis lists its supporting and contradicting clue ids, and the
     entities involved with their roles.
3. **Requests.** For signature metrics it cannot observe, the agent posts a REQUEST
   (`metric:<name>`, with the scope's entity ids), which is routed to whichever agent serves it.
4. **Stances.** For every other agent's hypothesis, the agent assesses the signature
   elements it *can* observe at the hypothesis' root:
   - satisfied elements → SUPPORT
   - violated elements → CONTRADICT, including `expect: normal` elements, so a significant
     deviation where the fault predicts normality counts *against* it
   - the strength of either is a weight ratio
5. **Responses.** It answers REQUESTs for its metrics with the matching clue ids.

## Connectivity agent

It reads every significant CLUE (where the symptoms are) and every HYPOTHESIS, and computes
the blast radius of the hypothesised root:

- **link:** everything below the downstream end, plus the upstream device
- **device:** its subtree and attached links
- **service:** its probes from anywhere

The share of symptomatic locations inside the blast radius decides its stance:

- **SUPPORT** at ≥ 60%, and only if at least two distinct locations are inside (no
  self-confirming evidence).
- **CONTRADICT** at ≤ 30%.
- **No stance** in between.

The stance note reports the lowest common upstream device of all symptoms, and whether they
are localised or widespread. Without a topology it posts `MISSING_TOPOLOGY` once and still
judges service hypotheses, whose blast radius does not need the graph.

## Hypothesis catalogue (`config/catalogue/hypotheses.yaml`)

Each entry declares:

- `locus`: the category (and optionally the types or names) where the root can be
- `signature`: metric, `expect` (deviates / normal), direction (above / below / changed /
  rising), scope, role (required / supporting), optional `group` (alternatives) and `quorum`
  (share of matching series that must agree, for multi-series scopes such as probes)
- relations: `competes_with` (mutually exclusive explanations) and `explains` (causal
  precedence, used in Phase 5 to merge symptom-level hypotheses into their cause)
- parametrised `actions` (`{root}`, `{upstream}`, `{downstream}`), plus a `rationale` and `source`

Entries cover every A6 scenario family (congestion, weak Wi-Fi, interface fault, DNS and DHCP
failure; interop failure is handled by the Translator, see D-010), plus device overload and
hardware failure from A1.

Scopes are named relations to the candidate root. They are resolved by
`netcoop/agents/scopes.py` from the topology: `root`, `root_upstream`, `root_downstream`,
`root_endpoints`, `attached_links`, `probes_of_root`, `probes_from_root`, `probes_downstream`,
`probe_paths`. Without topology only the root-local scopes resolve. Relational evidence is
then "unknown", never guessed.

## Measured behaviour (held-out seeds 3–4, every 4th run, intensity 0.25–1.0, all noise and missing levels)

| family | runs | true fault proposed at true location | other hypotheses per run |
|---|---|---|---|
| normal | 18 | n/a | 0.17 |
| link_congestion | 18 | 72% | 0.17 |
| weak_wifi | 18 | 56% | 0.00 |
| interface_fault | 18 | 100% | 1.83 (sibling links, hardware_failure) |
| dns_dhcp_failure | 18 | 89% | 0.06 |
| interop_failure | 18 | 56% (≈1 in 5 have a *normal* underlying state, counted as misses here) | 0.56 |

- **Misses** are dominated by intensity-0.25 faults at noise ≥ 0.1: the effect is smaller than
  the noise, and abstaining is correct.
- **Competing hypotheses** (most visibly for interface faults) are expected. Resolving them is
  the correlator's job (Phase 5).
- **Full evaluation:** the full-suite numbers, with the confusion matrix and calibration,
  come in Phase 8.
