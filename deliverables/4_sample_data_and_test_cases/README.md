# Sample data and test cases

## Sample inputs: `sample_data/`

Nine labelled runs of campus-network telemetry, from fresh seeds never used for training. Each
folder holds:
- the raw telemetry (JSONL, or CSV for the legacy export)
- `topology.json` or `topology_edges.csv`
- `meta.json` with the ground truth, which the agents never see

| folder | scenario | NetCoop outcome |
|---|---|---|
| `normal__s500__i0.5__n0.1__m0.0` | **normal network operation** | no fault detected |
| `link_congestion__s500__i1.0__n0.0__m0.0` | link congestion | diagnosed, confidence 1.00 |
| `link_congestion__s500__i0.25__n0.0__m0.0` | faint link congestion | not enough evidence (honest abstention) |
| `interface_fault__s500__i0.5__n0.1__m0.0` | interface fault | diagnosed after a courtroom tie-break |
| `dns_dhcp_failure__s500__i1.0__n0.0__m0.0` | DHCP service failure | diagnosed |
| `weak_wifi__s500__i1.0__n0.0__m0.0` | weak Wi-Fi signal | diagnosed |
| `interop_failure__s500__i0.5__n0.1__m0.0` | DNS failure, exported in a **legacy CSV format** | diagnosed |
| `device_overload__s100__i1.0__n0.0__m0.0` | device overload | diagnosed |
| `hardware_failure__s100__i1.0__n0.0__m0.0` | hardware failure (never seen in training) | not enough evidence; the courtroom defers |

The folder name encodes the generator settings:
`<scenario>__s<seed>__i<intensity>__n<noise>__m<missing-data rate>`.
[sample_data/README.md](sample_data/README.md) explains how to regenerate them byte for byte.

Try one:

```bash
netcoop run data/samples/link_congestion__s500__i1.0__n0.0__m0.0 -v
```

## Example reports: `example_reports/`

Final diagnostic reports, each in two forms: `report.json` (schema-valid) and `report.md`
(readable).

| report | outcome |
|---|---|
| `diagnosed_link_congestion` | diagnosed |
| `diagnosed_dns_failure` | diagnosed |
| `deferred_hardware_failure` | abstained after the courtroom deferred |

## Test cases

The tests are in the repository's [`tests/`](../../tests/) folder. There are **246 tests**,
counting each parametrised case.

[`test_run_output.txt`](test_run_output.txt) is a real full run: `246 passed in 96.87s`.

Run them from the repository root:

```bash
pytest
```

| test module | what it checks |
|---|---|
| `test_acceptance.py` | every minimum acceptance criterion of the problem statement (A10) |
| `test_protocol.py` | vocabulary, message models, round trips, validation, protocol versions |
| `test_translator.py` | Translator layers, canonical correctness, the 22-kind mutated corpus |
| `test_properties.py` | property-based: the Translator never raises and always emits valid messages |
| `test_orchestrator.py` | case board, rounds, routing, failure isolation, tracing, replay |
| `test_agents.py` | detection library, calibration, catalogue, specialist and connectivity agents |
| `test_correlation.py` | evidence model, calibration, decision policy, abstention on degraded evidence |
| `test_courtroom.py` | tie-break trigger, rubric, resolve-or-defer, deterministic transcript |
| `test_reporting.py` | schema-valid reports, evidence traced to observations, actions |
| `test_phase9.py` | pause/resume, human review, extensions and plugins, MCP server, external agents |
| `test_samples.py` | every sample regenerates byte for byte; every demo scene gives its expected outcome |
| `test_web.py` | dashboard server: live diagnosis stream, run details, file-access limits, local fonts |
| `test_generator.py`, `test_foundation.py` | data generator, justified-config loader, CLI errors |

The same tests run on GitHub Actions for every push, together with lint, strict type checks and
a schema freshness check.
