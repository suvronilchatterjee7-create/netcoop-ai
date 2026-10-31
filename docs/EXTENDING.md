# Extending NetCoop: new faults, agents and integrations without engine changes

NetCoop has three extension points, all opt-in and all additive. An extension can add
entries, but it cannot redefine shipped ones, so it cannot silently change existing
behaviour.

| what | where | code? |
|---|---|---|
| a new **fault type** | `vocabulary/hypothesis_types.yaml` + `catalogue/hypotheses.yaml` in an extension directory | no |
| a new **data-defined agent** (runs the generic specialist engine) | `catalogue/agents.yaml` in an extension directory | no |
| a new **code agent** | `plugins/*.py` in an extension directory, or a module listed in `NETCOOP_PLUGINS` | yes, a small class |
| an **external agent** (another tool, a probe, an MCP client) | the MCP `diagnose` tool with a capability card + messages (protocol 1.0 lite or 2.0) | none on our side |

Activate an extension directory with `NETCOOP_EXTENSIONS=<dir>[;<dir>…]` (the OS path
separator).

## Tutorial: add "AP client overload" (shipped in `examples/extension/`)

**1. Declare the fault type**, in `vocabulary/hypothesis_types.yaml`:

```yaml
version: "1.0"
hypothesis_types:
  ap_client_overload: {kind: fault, family: null, description: "Too many stations on one AP."}
```

**2. Describe what it predicts**, in `catalogue/hypotheses.yaml`:

- **where the root can be:** an access point
- **what it predicts:**
  - associated clients above normal (required)
  - retransmissions up and slower service from that AP (supporting)
  - RSSI staying *normal* (supporting), which is what separates it from weak Wi-Fi
- **what it competes with:** `weak_wifi_signal`
- **actions**, templated with `{root}`

See the shipped file for the full entry.

**3. Optionally add an agent that watches the relevant metric**, in `catalogue/agents.yaml`:

```yaml
version: "1.0"
specialists:
  client_load:
    description: "Client Load agent: number of associated stations per access point."
    metrics: [associated_clients]
    optional: true
    rationale: "Capacity view of the WLAN, separate from radio quality."
    source: "docs/EXTENDING.md tutorial"
```

**4. Run with the extension:**

```bash
NETCOOP_EXTENSIONS=examples/extension netcoop run <run-dir>
```

What happens, with no engine change:

- **The new agent registers itself.** `client_load` is created from its card.
- **Existing agents pick up the new fault.** An agent may propose any fault whose required
  metrics it observes, so the Wireless/Service agent now proposes `ap_client_overload` as well.
- **Stances and correlation just work.** Other agents support or contradict it through the
  same signature machinery, and the correlator scores it.
- **The engine is honest about having no training data.** With none for the new type, the
  correlator scores it with the pooled (role, expect) likelihood ratios and the global prior.
  The courtroom's under-trained rule applies, and the report names it as the best
  explanation, but abstains unless the evidence clears the calibrated accept threshold.
- **Diagnosis needs labelled examples.** To let the system *diagnose* it, generate labelled
  examples and run `netcoop fit`.

`tests/test_phase9.py::test_new_fault_and_agent_from_data_only` checks all of this, with and
without the extension.

## Code agents

A code agent is any class with a capability card and a `step` method:

```python
from netcoop.agents.base import Agent, AgentContext
from netcoop.agents.registry import register_agent
from netcoop.protocol.capability import AgentRole, CapabilityCard
from netcoop.protocol.common import MessageType as T


@register_agent
class MyAgent(Agent):
    card = CapabilityCard(
        agent_id="my-agent", version="0.1.0", role=AgentRole.SPECIALIST,
        description="what it is responsible for", protocol_versions=("2.0",),
        consumes_types=(T.OBSERVATION, T.HYPOTHESIS), consumes_metrics=("latency",),
        produces_types=(T.CLUE, T.SUPPORT, T.CONTRADICT),
    )

    def step(self, inbox, ctx: AgentContext) -> None:
        ...  # read the inbox and ctx.query(...), then post with ctx.post(T.CLUE, payload, parent=...)
```

Put it in `<extension>/plugins/my_agent.py`, or make it importable and set
`NETCOOP_PLUGINS=my_package.my_agent`. The orchestrator then:

- delivers messages according to its card
- routes REQUESTs it can serve
- isolates it if it crashes or hangs
- traces everything it posts

## External agents (MCP)

`netcoop mcp` serves NetCoop over stdio as an MCP server:

- **tools:** `diagnose`, `translate`, `list_runs`, `get_report`, `get_trace`, `get_topology`,
  `review_actions`
- **resources:** the message JSON Schema, the metric vocabulary and the fault catalogue

An external agent joins a diagnosis by passing `external_card` (a capability card) and
`external_messages` (CLUE, HYPOTHESIS or ERROR messages, in protocol **1.0 lite** or 2.0) to
`diagnose`:

1. **Upgrade:** a bridge upgrades the messages through the version adapters.
2. **Post:** it posts them under the agent's own id in round 1.
3. **Respond:** the built-in agents respond. Example from the tests: a lite-protocol site-survey
   probe proposes `weak_wifi_signal` at an AP; Performance and Connectivity support it, and the
   final report diagnoses it, with the probe among the evidence sources.

To register the server with an MCP client such as Claude Code:

```bash
claude mcp add netcoop -- netcoop mcp
```

## Rules an extension must follow

- **Use only the vocabulary.** Metric names and units must come from
  `data/vocabulary/metrics.yaml`. Extensions add fault types, signatures and agents, not
  metrics, so the Translator's mapping stays the single place where source fields are
  interpreted.
- **Be additive.** Existing keys cannot be redefined (`ValueError`).
- **Justify every entry.** Every catalogue entry needs a `rationale` and a `source`, as in
  the shipped catalogue.
