# Demo video script (about 4 minutes)

Everything on screen comes from `netcoop demo --step` (scenes in `config/demo.yaml`, samples
in `data/samples/`). Each scene checks its expected outcome. Rehearse with `netcoop demo`:
exit code 0 means every scene still behaves as scripted (`tests/test_samples.py` checks it too).

**Setup before recording.**

- Use a terminal at least 160 columns wide with a large font.
- Run `netcoop demo` once beforehand, so the first scene is not slowed by imports.
- Have `runs/demo/inc-31fb4b6e2e27/report.md` open in an editor tab for scene 1.
- Have `docs/EVALUATION.md` open in an editor tab for scene 6.

| time | on screen | say |
|---|---|---|
| 0:00-0:20 | README architecture diagram | "NetCoop diagnoses network faults with cooperating agents. They speak one versioned protocol on a shared case board. The output is one explainable report, or an honest 'not enough evidence'." |
| 0:20-1:10 | **Scene 1**, link congestion: capability counts, then the decision chain | "Eleven participants announce capability cards. The Translator turns raw telemetry into 406 canonical observations. The specialists post 457 clues, including the 'checked, normal' ones. Performance proposes link congestion and REQUESTs the metrics it can't see. The infrastructure and wireless agents answer, and every agent posts a stance. Each message points to its cause, so you can follow the arrows." |
| 1:10-1:30 | Scene 1 report and replay; open `report.md` | "One cause, at one link. Every evidence line names the baseline it was compared with and the config key behind it. The actions name real devices. The trace replays and verifies byte for byte." |
| 1:30-2:00 | **Scene 2**, legacy CSV | "A different exporter: CSV, other field names, other units. The declarative mapping recovers every series with zero errors, and the same agents find a DNS failure. We tested this against 22 kinds of schema corruption." |
| 2:00-2:30 | **Scene 3**, faint congestion | "This is a real fault, but faint. No candidate reaches the calibrated operating point, so NetCoop abstains and says what data would settle it. That is why 98.6% of its claims are right." |
| 2:30-3:05 | **Scene 4**, courtroom resolved | "An interface fault next to an access point also looks like a hardware failure of that AP. The courtroom scores only discriminating evidence. The interface fault is confirmed, and the hardware failure is listed as an alternative." |
| 3:05-3:30 | **Scene 5**, courtroom deferred | "Here the truth is a hardware failure, a type with no training data. The evidence leans toward it, but the calibrated model cannot vouch for it, so the judge defers instead of guessing. Over 120 such runs: zero wrong claims." |
| 3:30-4:00 | **Scene 6**, metrics; then EVALUATION.md robustness tables | "On 1,080 fresh test runs: 77% accuracy, 98.6% precision of claims, and 100% root localisation. Precision stays above 95% with three stacked interop mutations. Every parameter is justified in config, and the whole system is reproducible. Thank you." |

**Optional cut-ins (if time allows).**

- `netcoop run <sample> --pause-after 1` then `netcoop resume runs/<id>`: the resumed trace is
  identical.
- `netcoop review runs/<id> --approve 1 --reviewer judge`: the decision is recorded as an ACK in the trace.
- `netcoop mcp`, shown connected from an MCP client.
