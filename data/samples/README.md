# Sample runs

Nine labelled runs committed so NetCoop can be tried without generating the full dataset
(`netcoop run data/samples/<run>`, `netcoop demo`). Each directory holds the raw generator
files and `meta.json` with the ground truth. They come from the **fresh test seeds (500)** and
the **ambiguity suite (seeds 100-109)**, never from training or development seeds.

| run | ground truth | dialect | NetCoop outcome | shows |
|---|---|---|---|---|
| `link_congestion__s500__i1.0__n0.0__m0.0` | link_congestion | native JSONL | diagnosed | full collaboration, trace, replay (demo scene 1) |
| `interop_failure__s500__i0.5__n0.1__m0.0` | dns_dhcp_failure | legacy CSV | diagnosed (DNS) | dialect recovery (scene 2) |
| `link_congestion__s500__i0.25__n0.0__m0.0` | link_congestion (faint) | native JSONL | insufficient_evidence | honest abstention (scene 3) |
| `interface_fault__s500__i0.5__n0.1__m0.0` | interface_fault | native JSONL | diagnosed, courtroom resolved | tie-break (scene 4) |
| `hardware_failure__s100__i1.0__n0.0__m0.0` | hardware_failure (untrained type) | native JSONL | insufficient_evidence, courtroom deferred | no guessing on unseen faults (scene 5) |
| `dns_dhcp_failure__s500__i1.0__n0.0__m0.0` | dns_dhcp_failure | native JSONL | diagnosed (DHCP) | service fault |
| `weak_wifi__s500__i1.0__n0.0__m0.0` | weak_wifi | native JSONL | diagnosed | wireless fault |
| `normal__s500__i0.5__n0.1__m0.0` | normal | native JSONL | no_fault_detected | healthy network |
| `device_overload__s100__i1.0__n0.0__m0.0` | device_overload | native JSONL | diagnosed | ambiguity-suite fault |

The run name encodes the generator parameters: `<family>__s<seed>__i<intensity>__n<noise>__m<missing rate>`.

## Regenerating

The generator is deterministic, so these files are reproducible byte for byte
(`tests/test_samples.py` checks this):

```bash
netcoop generate --out data/test --seed 500        # main families, seed 500 (whole grid)
netcoop courtroom-eval                             # also writes the ambiguity suite to data/ambiguity/
```

or a single run from Python:

```python
from netcoop.generation import load_adapter
load_adapter().generate(scenario="link_congestion", seed=500, intensity=1.0, noise=0.0,
                        missing_rate=0.0, out_dir=Path("out"))
```
