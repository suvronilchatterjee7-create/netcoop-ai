# Protocol field reference

Generated from the Pydantic models by `netcoop schemas` (protocol 2.0, vocabulary 1.0). Do not edit by hand. Rules and semantics: PROTOCOL.md.

## Envelope and messages

### Envelope

Fields common to every message; `type` and `payload` are added per message type.

| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `protocol` | const | no (default `'netcoop'`) |  | `netcoop` | Protocol name; always 'netcoop'. |
| `protocol_version` | const | no (default `'2.0'`) |  | `2.0` | Wire-format version of this message. |
| `schema_version` | string | yes |  |  | Controlled-vocabulary version the payload's terms refer to. |
| `msg_id` | string | yes |  | min len 1 | Unique message id; content hash when built by make_message. |
| `correlation_id` | string | yes |  | min len 1 | Incident id shared by every message of one diagnosis run. |
| `causation_id` | string or null | no (default `None`) |  |  | msg_id of the message that caused this one (null = root). |
| `depth` | integer | no (default `0`) |  | >=0 | Causation depth: 0 for roots, parent depth + 1 otherwise. |
| `sender` | string | yes |  | min len 1 | agent_id of the sender. |
| `recipient` | string | no (default `'board'`) |  |  | agent_id of the recipient, or 'board' for a shared post. |
| `timestamp` | datetime (ISO-8601, tz) | yes |  |  | Creation time, ISO-8601 UTC (excluded from msg_id). |
| `adaptations` | list[string] | no (default `()`) |  |  | Version conversions applied, e.g. '1.0->2.0', and any lossy fields. |
| `type` | enum | yes |  | `OBSERVATION`, `TOPOLOGY`, `CLUE`, `HYPOTHESIS`, `SUPPORT`, `CONTRADICT`, `REQUEST`, `RESPONSE`, `ERROR`, `ACK`, `CAPABILITY`, `VERDICT`, `REPORT` | Message type; fixes the payload model. |
| `payload` | Any | yes |  |  | Type-specific payload. |

### ObservationPayload

A canonical time series of one metric on one entity (output of the Translator).

| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `entity` | [EntityRef](#entityref) | yes |  |  | Entity the metric describes. |
| `metric` | string | yes |  |  | Canonical metric name (metrics.yaml). |
| `unit` | string | yes |  |  | Canonical unit of the metric; must equal the vocabulary unit. |
| `observed_from` | string or null | no (default `None`) |  |  | Vantage point entity_id for probe-style metrics (e.g. service checks). |
| `points` | list[[Point](#point)] | yes |  | min len 1 | Samples in time order. |
| `sources` | list[[SourceRef](#sourceref)] | no (default `()`) |  |  | Where the samples came from (provenance). |
| `quality` | [DataQuality](#dataquality) | yes |  |  | Data-quality assessment of this series. |

### TopologyPayload

The network graph as reported by the input data.

| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `nodes` | list[[TopologyNode](#topologynode)] | yes |  |  | All known devices/services. |
| `edges` | list[[TopologyEdge](#topologyedge)] | yes |  |  | All known links. |
| `upstream_root` | string or null | no (default `None`) |  |  | entity_id of the topology root (core), if known. |
| `sources` | list[[SourceRef](#sourceref)] | no (default `()`) |  |  | Where the topology came from. |
| `quality` | [DataQuality](#dataquality) | yes |  |  | Data-quality assessment of the topology. |

### CluePayload

One piece of evidence: a metric on an entity deviates (or explicitly does not).

| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `entity` | [EntityRef](#entityref) | yes |  |  | Entity the evidence is about. |
| `metric` | string | yes |  |  | Canonical metric name. |
| `statistic` | enum | yes |  | `mean`, `median`, `max`, `min`, `last`, `slope`, `fraction`, `unspecified` | How `value` summarises the window. |
| `value` | number or string | yes |  |  | Summary value. Level stats: metric unit; slope: unit/interval; fraction: ratio. |
| `unit` | string | yes |  |  | Unit of `value` (see `statistic`). |
| `comparison` | [Comparison](#comparison) | yes |  |  | What `value` was compared with. |
| `direction` | enum | yes |  | `above`, `below`, `changed` | Direction of the deviation relative to the reference. |
| `deviation` | number | yes |  | >=0 | Normalised deviation magnitude (see `deviation_unit`); 0 = none. |
| `deviation_unit` | string | yes |  |  | Normalisation used, e.g. 'robust_z', 'ratio', 'percentage_points'. |
| `significant` | boolean | yes |  |  | Detector judged the deviation significant (False = explicit negative evidence). |
| `persistence` | number or null | no (default `None`) | ratio | >=0, <=1 | Share of window samples that deviate; null if unknown. |
| `window` | [TimeWindow](#timewindow) | yes |  |  | Time window the evidence covers. |
| `observed_from` | string or null | no (default `None`) |  |  | Vantage point, for probe-style metrics. |
| `source_observation_ids` | list[string] | yes |  | min len 1 | msg_ids of the OBSERVATIONs used. |
| `data_quality` | number | yes | ratio | >=0, <=1 | Quality of the underlying observations. |

### HypothesisPayload

A suspect: a candidate root cause with its supporting and contradicting evidence.

| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `hypothesis_type` | string | yes |  |  | Hypothesis type (hypothesis_types.yaml), a fault or 'normal'. |
| `entities` | list[[HypothesisEntity](#hypothesisentity)] | yes |  |  | Affected entities with roles. |
| `local_confidence` | number | yes | ratio | >=0, <=1 | Proposer's own confidence, before correlation. |
| `confidence_method` | string | yes |  |  | Key of the documented method that produced local_confidence. |
| `supporting_clue_ids` | list[string] | no (default `()`) |  |  | msg_ids of CLUEs that support it. |
| `contradicting_clue_ids` | list[string] | no (default `()`) |  |  | msg_ids of CLUEs that contradict it. |

### StancePayload

SUPPORT or CONTRADICT: one agent's evidence bearing on another agent's post.

| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `target_msg_id` | string | yes |  |  | msg_id of the CLUE or HYPOTHESIS being supported/contradicted. |
| `clue_ids` | list[string] | yes |  | min len 1 | CLUEs that justify the stance (the sender's own, or cited symptoms). |
| `strength` | number | yes | ratio | >=0, <=1 | How strongly the evidence bears on the target. |
| `reason_code` | string | yes |  |  | Machine-readable reason, e.g. 'corroborates', 'transport_healthy'. |
| `note` | string | no (default `''`) |  |  | Short human-readable explanation. |

### RequestPayload

Directed query for targeted evidence, routed by capability.

| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `capability` | string | yes |  | pattern `^(metric\|analysis):[a-z_]+$` | Requested capability: 'metric:<metric>' or 'analysis:<name>'. |
| `entity_ids` | list[string] | no (default `()`) |  |  | Entities to evaluate (empty = all relevant). |
| `params` | map[string, string or number or integer or boolean] | no (default `{}`) |  |  | Capability-specific parameters. |
| `reason` | string | yes |  |  | Why the evidence is needed (e.g. 'discriminate link_congestion vs ...'). |

### ResponsePayload



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `request_msg_id` | string | yes |  |  | msg_id of the REQUEST answered. |
| `status` | enum | yes |  | `ok`, `no_data`, `unsupported`, `failed` | Outcome of the request. |
| `result_msg_ids` | list[string] | no (default `()`) |  |  | msg_ids of CLUEs/HYPOTHESES posted in answer. |
| `detail` | string | no (default `''`) |  |  | Explanation, especially for non-ok status. |

### ErrorPayload



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `code` | enum | yes |  | `MALFORMED_INPUT`, `MISSING_FIELD`, `TYPE_MISMATCH`, `UNKNOWN_FIELD`, `UNKNOWN_UNIT`, `AMBIGUOUS_UNIT`, `IMPLAUSIBLE_VALUE`, `STALE_DATA`, `CLOCK_SKEW`, `UNKNOWN_ENTITY`, `MISSING_TOPOLOGY`, `INCOMPATIBLE_SCHEMA`, `INCOMPATIBLE_VERSION`, `UNSUPPORTED_MESSAGE_TYPE`, `UNSUPPORTED_REQUEST`, `AGENT_TIMEOUT`, `AGENT_FAILURE`, `BUDGET_EXCEEDED`, `DUPLICATE_SAMPLE`, `INAPPLICABLE_METRIC` | Typed error code. |
| `severity` | enum | yes |  | `fatal`, `recoverable`, `warning` | Impact of the error on the run. |
| `message` | string | yes |  |  | Human-readable description. |
| `related_msg_id` | string or null | no (default `None`) |  |  | Message the error concerns, if any. |
| `source` | [SourceRef](#sourceref) or null | no (default `None`) |  |  | Input location the error concerns, if any. |
| `context` | map[string, string or number or integer or boolean] | no (default `{}`) |  |  | Structured details (field, value, expected, ...). |

### AckPayload



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `acked_msg_id` | string | yes |  |  | msg_id being acknowledged. |
| `status` | enum | yes |  | `accepted`, `duplicate`, `rejected` | Whether the board/recipient accepted it. |
| `reason` | string | no (default `''`) |  |  | Reason for duplicate/rejected. |

### CapabilityPayload



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `card` | [CapabilityCard](#capabilitycard) | yes |  |  | The sender's capability card. |

### VerdictPayload



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `decision` | enum | yes |  | `diagnosed`, `insufficient_evidence`, `no_fault_detected` | Outcome of correlation / courtroom. |
| `hypothesis_type` | string or null | no (default `None`) |  |  | Winning hypothesis type, null unless diagnosed. |
| `entities` | list[[HypothesisEntity](#hypothesisentity)] | no (default `()`) |  |  | Entities of the winning hypothesis. |
| `confidence` | number | yes | ratio | >=0, <=1 | Calibrated confidence in the decision. |
| `confidence_category` | string | yes |  |  | Category from config (e.g. high/medium/low). |
| `ranking` | list[[RankedHypothesis](#rankedhypothesis)] | no (default `()`) |  |  | All candidates, best first. |
| `method` | string | yes |  |  | 'correlation' or 'courtroom'. |
| `missing_evidence` | list[string] | no (default `()`) |  |  | Data that would resolve an abstention. |
| `rationale` | list[string] | no (default `()`) |  |  | Decision-rule codes that fired, in order. |

### ReportPayload



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `report` | [Report](#report) | yes |  |  | The unified diagnostic report (A7 schema + extensions). |

### CapabilityCard



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `agent_id` | string | yes |  | pattern `^[a-z][a-z0-9_.-]*$` | Unique agent identifier; used as `sender`/`recipient`. |
| `version` | string | yes |  |  | Agent implementation version (semver). |
| `role` | enum | yes |  | `translator`, `specialist`, `correlator`, `adjudicator`, `reporter`, `external` | Kind of agent. |
| `description` | string | yes |  |  | What the agent is responsible for. |
| `protocol_versions` | list[string] | yes |  | min len 1 | Protocol versions the agent can speak. |
| `consumes_types` | list[enum] | yes |  | `OBSERVATION`, `TOPOLOGY`, `CLUE`, `HYPOTHESIS`, `SUPPORT`, `CONTRADICT`, `REQUEST`, `RESPONSE`, `ERROR`, `ACK`, `CAPABILITY`, `VERDICT`, `REPORT` | Message types the agent wants delivered. |
| `consumes_metrics` | list[string] | no (default `()`) |  |  | Canonical metrics it analyses ('*' = all). |
| `produces_types` | list[enum] | yes |  | `OBSERVATION`, `TOPOLOGY`, `CLUE`, `HYPOTHESIS`, `SUPPORT`, `CONTRADICT`, `REQUEST`, `RESPONSE`, `ERROR`, `ACK`, `CAPABILITY`, `VERDICT`, `REPORT` | Message types the agent may emit. |
| `hypothesis_types` | list[string] | no (default `()`) |  |  | Hypothesis types it may propose. |
| `serves` | list[string] | no (default `()`) |  |  | REQUEST capabilities it answers: 'metric:<name>', 'analysis:<name>', or 'metric:*' (any metric in consumes_metrics). |
| `optional` | boolean | no (default `False`) |  |  | If true, absence or inactivity does not lower confidence. |
| `activation_metrics` | list[string] | no (default `()`) |  |  | Agent runs only if at least one of these metrics is observed (empty = always). |

### Report



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `incident_id` | string | yes |  |  | Incident identifier. |
| `status` | enum | yes |  | `diagnosed`, `insufficient_evidence`, `no_fault_detected`, `failed` | Overall outcome. |
| `suspected_root_cause` | string | yes |  |  | Root cause in words, or why none can be named. |
| `confidence` | number | yes | ratio | >=0, <=1 | Calibrated confidence in the status/root cause. |
| `affected_devices` | list[string] | yes |  |  | entity_ids of affected devices/links/services. |
| `supporting_evidence` | list[[EvidenceItem](#evidenceitem)] | yes |  |  | Evidence behind the conclusion. |
| `alternative_causes` | list[string] | yes |  |  | Competing explanations with non-trivial support. |
| `recommended_actions` | list[string] | yes |  |  | Corrective actions for human review. |
| `evidence_sources` | list[string] | yes |  |  | agent_ids whose evidence was used. |
| `limitations` | list[string] | yes |  |  | Data problems, missing agents, uncertainty. |
| `x_netcoop` | [ReportExtensions](#reportextensions) or null | no (default `None`) |  |  | NetCoop extensions (namespaced). |

### EntityRef



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `entity_id` | string | yes |  | min len 1 | Identifier of the entity exactly as it appears in the input data. |
| `entity_type` | string | yes |  |  | Entity type from the controlled vocabulary (entity_types.yaml). |

### Point



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `t` | datetime (ISO-8601, tz) | yes |  |  | Sample timestamp, ISO-8601 UTC. |
| `v` | number or string | yes |  |  | Sample value in the observation's canonical unit (str for enum metrics). |
| `src` | integer or null | no (default `None`) |  |  | Index into the observation's `sources` list for this sample. |

### SourceRef



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `source` | string | yes |  |  | Input file or stream name the data came from. |
| `dialect` | string | yes |  |  | Detected input dialect / mapping profile used to read it. |
| `locator` | string | yes |  |  | Position inside the source, e.g. 'line:42' or 'row:7'. |
| `raw_field` | string or null | no (default `None`) |  |  | Original field name before mapping, if different. |

### DataQuality



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `score` | number | yes | ratio | >=0, <=1 | Overall quality (combination documented in docs/SCORING.md). |
| `completeness` | number | yes | ratio | >=0, <=1 | Share of expected samples/fields present. |
| `freshness` | number | yes | ratio | >=0, <=1 | 1 = current, decays with staleness. |
| `plausibility` | number | yes | ratio | >=0, <=1 | Share of values inside physical ranges. |
| `mapping_certainty` | number | yes | ratio | >=0, <=1 | 1 = exact field/unit mapping; lower when inferred. |
| `issues` | list[string] | no (default `()`) |  |  | Machine-readable issue codes (ErrorCode values). |

### TopologyNode



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `entity` | [EntityRef](#entityref) | yes |  |  | The node. |
| `attributes` | map[string, string or number or integer or boolean] | no (default `{}`) |  |  | Free-form source attributes (zone, tier, ...). |

### TopologyEdge



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `link_id` | string | yes |  | min len 1 | entity_id of the link entity this edge represents. |
| `a` | string | yes |  |  | entity_id of one endpoint (the upstream end when `directed`). |
| `b` | string | yes |  |  | entity_id of the other endpoint (the downstream end when `directed`). |
| `directed` | boolean | yes |  |  | True if a is known to be upstream of b. |
| `capacity` | number or null | no (default `None`) | Mbit/s | >=0 | Nominal capacity. |

### Comparison



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `basis` | enum | yes |  | `threshold`, `baseline` | Whether the value was compared with a fixed threshold or a baseline. |
| `reference_value` | number or string or null | no (default `None`) |  |  | The threshold or baseline centre used, in the clue's unit. |
| `spread` | number or null | no (default `None`) |  |  | Baseline spread (e.g. scaled MAD) used for normalisation. |
| `config_key` | string | yes |  | min len 1 | Config key (or calibration key) the reference came from. |
| `method` | string | yes |  |  | Detector that produced the comparison (documented in docs/SCORING.md). |

### TimeWindow



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `start` | datetime (ISO-8601, tz) | yes |  |  | Start of the window (inclusive), ISO-8601 with timezone. |
| `end` | datetime (ISO-8601, tz) | yes |  |  | End of the window (inclusive), ISO-8601 with timezone. |

### HypothesisEntity



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `entity` | [EntityRef](#entityref) | yes |  |  | Entity involved in the hypothesis. |
| `role` | enum | yes |  | `root`, `symptom`, `context` | Role of the entity in the hypothesis. |

### RankedHypothesis



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `hypothesis_type` | string | yes |  |  | Hypothesis type. |
| `entities` | list[[HypothesisEntity](#hypothesisentity)] | yes |  |  | Entities of the (merged) hypothesis. |
| `hypothesis_msg_ids` | list[string] | yes |  |  | HYPOTHESIS messages merged into this candidate. |
| `score` | number | yes |  |  | Raw evidence score (docs/SCORING.md). |
| `confidence` | number | yes | ratio | >=0, <=1 | Calibrated confidence. |

### EvidenceItem



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `metric` | string | yes |  |  | Canonical metric name. |
| `value` | number | yes |  |  | Observed summary value, in the unit given in x_netcoop provenance. |
| `interpretation` | string | yes |  |  | What the value means relative to its baseline/threshold. |

### ReportExtensions



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `confidence_category` | string | yes |  |  | Confidence category (boundaries in config). |
| `evidence_provenance` | list[[EvidenceProvenance](#evidenceprovenance)] | no (default `()`) |  |  | Trace of each evidence item. |
| `alternatives_scored` | list[[ScoredAlternative](#scoredalternative)] | no (default `()`) |  |  | Scores of alternative causes. |
| `data_quality` | [DataQualitySummary](#dataqualitysummary) or null | no (default `None`) |  |  | Input quality summary. |
| `courtroom` | [CourtroomSummary](#courtroomsummary) or null | no (default `None`) |  |  | Tie-break summary, if relevant. |
| `missing_evidence` | list[string] | no (default `()`) |  |  | What extra data would resolve an abstention. |
| `score_breakdown` | list[[ScoreTerm](#scoreterm)] | no (default `()`) |  |  | Itemised log-odds of the reported (or best) candidate. |
| `simulated_remediation` | list[[SimulatedAction](#simulatedaction)] | no (default `()`) |  |  | Dry-run effects of the recommended actions. |
| `manifest` | [RunManifest](#runmanifest) or null | no (default `None`) |  |  | Reproducibility manifest. |

### EvidenceProvenance



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `evidence_index` | integer | yes |  | >=0 | Index into supporting_evidence. |
| `clue_id` | string | yes |  |  | msg_id of the CLUE behind this evidence item. |
| `agent` | string | yes |  |  | agent_id that produced the clue. |
| `entity_id` | string | yes |  |  | Entity the evidence is about. |
| `unit` | string | yes |  |  | Unit of `value`. |
| `reference_value` | number or string or null | yes |  |  | Threshold or baseline compared against. |
| `config_key` | string | yes |  |  | Config / calibration key of the reference. |
| `observation_ids` | list[string] | yes |  |  | OBSERVATION msg_ids the clue was computed from. |

### ScoredAlternative



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `cause` | string | yes |  |  | Hypothesis type and location, same wording as alternative_causes. |
| `score` | number | yes |  |  | Raw evidence score. |
| `confidence` | number | yes | ratio | >=0, <=1 | Calibrated confidence. |

### DataQualitySummary



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `overall` | number | yes | ratio | >=0, <=1 | Aggregate input quality. |
| `per_entity` | map[string, number] | no (default `{}`) |  |  | Quality per entity_id. |
| `issues` | map[string, integer] | no (default `{}`) |  |  | Count of each issue code seen. |

### CourtroomSummary



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `invoked` | boolean | yes |  |  | Whether the tie-break ran. |
| `contenders` | list[string] | no (default `()`) |  |  | Hypotheses that were argued. |
| `rounds` | integer | no (default `0`) |  | >=0 | Debate rounds held. |
| `outcome` | string | no (default `''`) |  |  | 'resolved' or 'deferred'. |
| `summary` | string | no (default `''`) |  |  | Short explanation of the ruling. |
| `transcript_msg_ids` | list[string] | no (default `()`) |  |  | Trace messages of the debate. |

### ScoreTerm



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `term` | string | yes |  |  | Score component: 'prior', a signature element, 'analytic stance' or 'evidence quality'. |
| `status` | string | yes |  |  | Status of the component (satisfied / violated / unknown, support / none, bin). |
| `contribution` | number | yes | log-odds |  | Contribution to the candidate's log-odds score. |

### SimulatedAction



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `action` | string | yes |  |  | Recommended action (same text as in recommended_actions). |
| `expected_effects` | list[string] | yes |  |  | What should change if the diagnosis is right and the action works. |
| `applied` | boolean | no (default `False`) |  |  | Always false: remediation is simulated, never executed. |

### RunManifest



| field | type | required | unit | allowed values / constraints | meaning |
|---|---|---|---|---|---|
| `incident_id` | string | yes |  |  | Incident (correlation_id) of the run. |
| `input_hash` | string | yes |  |  | SHA-256 over the input files. |
| `config_hash` | string | yes |  |  | SHA-256 over config/*.yaml. |
| `code_version` | string | yes |  |  | netcoop package version (and git revision if available). |
| `protocol_version` | string | yes |  |  | Protocol version used on the board. |
| `vocabulary_version` | string | yes |  |  | Controlled vocabulary version. |
| `seed` | integer | yes |  |  | Seed for any randomness. |

## Message types

| type | payload | purpose |
|---|---|---|
| `OBSERVATION` | [ObservationPayload](#observationpayload) | Canonical telemetry series (Translator output). |
| `TOPOLOGY` | [TopologyPayload](#topologypayload) | Network graph from the input data. |
| `CLUE` | [CluePayload](#cluepayload) | A piece of evidence. |
| `HYPOTHESIS` | [HypothesisPayload](#hypothesispayload) | A candidate root cause. |
| `SUPPORT` | [StancePayload](#stancepayload) | Evidence supporting another agent's post. |
| `CONTRADICT` | [StancePayload](#stancepayload) | Evidence contradicting another agent's post. |
| `REQUEST` | [RequestPayload](#requestpayload) | Directed evidence query, routed by capability. |
| `RESPONSE` | [ResponsePayload](#responsepayload) | Answer to a REQUEST. |
| `ERROR` | [ErrorPayload](#errorpayload) | Typed error. |
| `ACK` | [AckPayload](#ackpayload) | Acknowledgement of a message. |
| `CAPABILITY` | [CapabilityPayload](#capabilitypayload) | Capability-card announcement. |
| `VERDICT` | [VerdictPayload](#verdictpayload) | Correlation / courtroom decision. |
| `REPORT` | [ReportPayload](#reportpayload) | Final unified report. |

## Controlled vocabulary

### Metrics

| metric | unit | kind | applies to | worse when | physical range | meaning |
|---|---|---|---|---|---|---|
| `latency` | ms | numeric | link | higher | [0.0, -] | One-way delay across a link (per-hop) or along a path, as reported by the source. |
| `jitter` | ms | numeric | link | higher | [0.0, -] | Variation in delay (packet delay variation) over the sampling interval. |
| `packet_loss` | percent | numeric | link | higher | [0.0, 100.0] | Share of packets lost on a wired link during the sampling interval. |
| `utilization` | percent | numeric | link | higher | [0.0, 100.0] | Share of link capacity in use during the sampling interval. |
| `throughput` | Mbit/s | numeric | link | none | [0.0, -] | Achieved data rate on a link during the sampling interval. |
| `link_capacity` | Mbit/s | numeric | link | lower | [0.0, -] | Nominal bandwidth of a link (static attribute). |
| `cpu_utilization` | percent | numeric | device | higher | [0.0, 100.0] | Device CPU load. |
| `memory_utilization` | percent | numeric | device | higher | [0.0, 100.0] | Device memory in use. |
| `egress_queue_drops` | count | numeric | device | higher | [0.0, -] | Packets dropped from egress queues during the sampling interval (delta, not cumulative). |
| `interface_in_errors` | count | numeric | device | higher | [0.0, -] | Inbound interface errors (CRC, framing, runts) during the sampling interval (delta). |
| `interface_out_errors` | count | numeric | device | higher | [0.0, -] | Outbound interface errors during the sampling interval (delta). |
| `device_status` | state | enum values: up, degraded, down | device | categorical |  | Operational state of the device or its monitored interface. |
| `rssi` | dBm | numeric | device | lower | [-120.0, 0.0] | Received signal strength at the wireless access point / client. |
| `snr` | dB | numeric | device | lower | [-20.0, 100.0] | Signal-to-noise ratio of the wireless channel. |
| `retransmission_rate` | percent | numeric | device | higher | [0.0, 100.0] | Share of wireless frames retransmitted. |
| `wireless_packet_loss` | percent | numeric | device | higher | [0.0, 100.0] | Share of wireless frames lost (distinct from wired packet_loss, see DATA_PROFILE notes). |
| `associated_clients` | count | numeric | device | higher | [0.0, -] | Number of stations associated with an access point (more than normal = contention). |
| `service_success_rate` | percent | numeric | service | lower | [0.0, 100.0] | Share of successful probes of a network service (DNS lookup, DHCP exchange) from a vantage point. |
| `service_response_time` | ms | numeric | service | higher | [0.0, -] | Response time of a network service probe from a vantage point. |

### Units

| dimension | canonical | unit | factor to canonical | aliases |
|---|---|---|---|---|
| time | ms | ms | 1 | msec, millisecond, milliseconds |
| time | ms | us | 0.001 | µs, usec, microsecond, microseconds |
| time | ms | s | 1000 | sec, second, seconds |
| proportion | percent | percent | 1 | %, pct |
| proportion | percent | ratio | 100 | fraction |
| data_rate | Mbit/s | Mbit/s | 1 | Mbps, mbps, Mb/s |
| data_rate | Mbit/s | kbit/s | 0.001 | kbps, Kbps, kb/s |
| data_rate | Mbit/s | Gbit/s | 1000 | Gbps, gbps, Gb/s |
| data_rate | Mbit/s | bit/s | 1e-06 | bps |
| power_level | dBm | dBm | 1 | dbm |
| power_ratio | dB | dB | 1 | db |
| count | count | count | 1 | packets, errors, drops, stations, clients |
| state | state | state | 1 | enum, status |

### Entity types

| type | category | meaning |
|---|---|---|
| `router` | device | Layer-3 forwarding device. |
| `switch` | device | Layer-2/3 switch (distribution or access). |
| `access_point` | device | Wireless access point. |
| `server` | device | Host providing a network service (e.g. DNS, DHCP). |
| `client` | device | End host or wireless station. |
| `device` | device | Device of unknown kind (used when the source does not say). |
| `link` | link | Connection between two devices; may be directed upstream->downstream. |
| `service` | service | Logical network service (e.g. dns, dhcp), observed from vantage points. |
| `segment` | segment | Group of entities (zone, VLAN, building) used for blast-radius statements. |

### Hypothesis types

| type | kind | scenario family | meaning |
|---|---|---|---|
| `link_congestion` | fault | link_congestion | Link carries more traffic than it can forward without queueing and loss. |
| `weak_wifi_signal` | fault | weak_wifi | Poor radio conditions (low RSSI/SNR) at an access point degrade wireless service. |
| `interface_fault` | fault | interface_fault | Physical or link-layer fault on an interface: rising errors, loss, instability. |
| `dns_service_failure` | fault | dns_dhcp_failure | DNS service fails or is slow while transport is healthy. |
| `dhcp_service_failure` | fault | dns_dhcp_failure | DHCP service fails or is slow while transport is healthy. |
| `device_overload` | fault | device_overload | Device CPU or memory exhaustion degrades forwarding or control plane. |
| `hardware_failure` | fault | hardware_failure | Device is down or failing as a whole (not a single interface). |
| `normal` | outcome | normal | No significant deviation from baseline was found. |
| `insufficient_evidence` | outcome | - | Evidence is too weak, too degraded or too ambiguous to name a root cause. |
