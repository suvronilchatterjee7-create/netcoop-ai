# Case board and orchestration

```bash
netcoop run data/generated/<family>/<run> -v     # diagnose; -v prints every board message
netcoop replay runs/<incident_id>                 # rebuild the board from the trace and verify it
```

```python
from netcoop.api import diagnose, run_diagnosis
report = diagnose(path)                                     # -> Report (A7 + x_netcoop)
result = run_diagnosis(path, on_event=print, out_dir=None)  # board, trace, manifest, live events
```

## Case board (`netcoop/board/board.py`)

The board is a shared, append-only log. Every accepted message gets a sequence number,
which is the board version. The board rejects (never raises on):

| rule | why |
|---|---|
| `correlation_id` must equal the incident | messages from different incidents cannot mix |
| a `msg_id` already on the board is a **duplicate** | idempotency: msg_ids are content hashes, so re-posting the same content is harmless |
| `causation_id` must already be on the board | causal chains are always complete and traceable |
| `depth` > `board.max_causation_depth` | loop prevention: agents reacting to each other's reactions run out of depth |
| more than `board.per_agent_round_budget` posts by one sender in one round | flood control; ingestion (round 0) and replay are exempt |

Agents read the board by type, metric, entity or sender (indexed), can walk `ancestors()`
(the causal chain to the root), and can `subscribe` with filters. A trace writer and the UI
event hook use subscriptions too.

## Agents and the registry

An agent is a plugin: a class with a `CapabilityCard` and a `step(inbox, ctx)` method,
registered with `@register_agent` in any module under `netcoop/agents/`. The orchestrator
never names an agent. Agents never write to the board directly: they call `ctx.post(...)`,
which builds a deterministic message with sender, incident, timestamp and causation filled
in, and the orchestrator commits it.

## A run

1. **Ingestion (round 0).**
   - Every participant's CAPABILITY card is posted, followed by the Translator's TOPOLOGY,
     OBSERVATIONs and ERRORs.
   - **Version negotiation:** an agent whose card does not list the board's protocol version
     is excluded with `INCOMPATIBLE_VERSION`.
   - **Activation:** an agent whose `activation_metrics` are absent from the data does not run.
     If it is not `optional`, that becomes a limitation in the report.
2. **Collaboration rounds 1..`max_rounds`.**
   - **Delivery:** each active agent receives the board messages committed since its last
     turn that its card `wants(type, metric)`. It also receives messages addressed to it, and
     REQUESTs whose capability it `can_serve`. It never receives its own posts.
   - **Concurrency:** agents with a non-empty inbox run concurrently on a thread pool.
   - **Determinism:** posts are committed in agent-id order once all steps finish, so results
     never depend on thread scheduling.
   - **Routing:** a REQUEST that no active agent can serve is answered by the orchestrator
     with a RESPONSE of status `unsupported`.
   - **Termination:** a round in which no agent posts anything is **convergence**. Reaching
     the round limit is reported as `BUDGET_EXCEEDED`.
3. **Failure isolation.**
   - An agent that raises, or does not finish within `agents.timeout_s`, has that round's
     output discarded. It is disabled for the rest of the run and reported
     (`AGENT_FAILURE` / `AGENT_TIMEOUT`).
   - Other agents continue, and the report lists the missing agent's evidence as a limitation.
   - Board rejections are aggregated into `BUDGET_EXCEEDED` warnings for each sender and reason.
4. **Closing stages.** The correlator posts the VERDICT, and the reporter posts the REPORT
   (caused by the VERDICT).

## Trace, manifest and replay

`runs/<incident_id>/` contains:

| file | content |
|---|---|
| `trace.jsonl` | one `{"seq", "round", "msg"}` line per accepted message, written as it is committed (a dashboard can tail it) |
| `manifest.json` | incident, input SHA-256 (over file names and bytes), config SHA-256, code version (package + git revision), protocol and vocabulary versions, seed, rounds, convergence, agents and versions, failed and inactive agents, message counts, rejections, trace SHA-256; wall-clock timing is kept separately |
| `report.json` | the final report |

The incident id defaults to `inc-<first 12 hex digits of the input hash>`. Message
timestamps are the data's reference time, never the wall clock, so **the same input and
config give a byte-identical trace** (this is tested).

`netcoop replay` re-posts every line into a fresh board and checks:

- the sequence numbers are in order
- every message is accepted
- re-serialising gives the same line
- the trace hash matches the manifest

This is also the basis for pause and resume: a board can be rebuilt from any trace prefix.

## Provisional stages

Until Phase 5 (scoring, calibration, decision policy) and Phase 7 (full reporting) land,
`ProvisionalCorrelator` ranks hypotheses by their proposers' confidence and **always
abstains** (`insufficient_evidence`, confidence 0, category `unrated`). Without a documented,
calibrated method, claiming a root cause would break requirement A2. `ProvisionalReporter`
already produces a schema-valid A7 report with provenance and aggregated limitations.

## Limits (config/orchestrator.yaml)

`rounds.max_rounds` 8, `board.max_causation_depth` 10, `board.per_agent_round_budget` 2000,
`agents.timeout_s` 30, `agents.max_workers` 4. Each is derived from the designed message
sequence or from data sizes; see the rationale in the file.

**Known limitation:** Python threads cannot be killed. A timed-out agent keeps its thread
until it returns, but its results are discarded and it is never called again.
