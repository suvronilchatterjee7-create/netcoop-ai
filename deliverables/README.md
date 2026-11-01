# NetCoop AI: deliverables

Interoperable multi-agent network fault diagnosis, built for the Agentic AI Hackathon at IIT
Bhubaneswar. This folder gathers every deliverable in one place.

| # | deliverable | where | contents |
|---|---|---|---|
| 1 | **Demo video** (3–5 min) | [`1_demo_video/`](1_demo_video/) | 4 min 25 s screen recording: end-to-end diagnosis, inter-agent communication, final report; plus the script and narration |
| 2 | **Source code repository** | [`2_source_code/`](2_source_code/) | complete source snapshot (zip), dependencies, setup and test instructions; live repo on GitHub |
| 3 | **Architecture documentation** | [`3_architecture_documentation/`](3_architecture_documentation/) | [ARCHITECTURE.md](3_architecture_documentation/ARCHITECTURE.md) plus protocol, orchestration, agents, scoring, courtroom, Translator, reporting and JSON Schemas |
| 4 | **Sample data and test cases** | [`4_sample_data_and_test_cases/`](4_sample_data_and_test_cases/) | normal operation plus 8 fault scenarios, example reports, the 246-test suite and its real output |
| 5 | **Working prototype** | [`5_working_prototype/`](5_working_prototype/) | how to run the CLI and the dashboard, and screenshots of the complete workflow |
| 6 | Evaluation results | [`6_evaluation_results/`](6_evaluation_results/) | accuracy, precision, robustness, ablations, calibration |

## Requirement checklist

| requirement | where to find it |
|---|---|
| Complete implementation | [2_source_code/](2_source_code/) and the repository's `netcoop/` folder |
| Dependencies | [2_source_code/README.md](2_source_code/README.md#dependencies) and `pyproject.toml` |
| Setup instructions | [2_source_code/README.md](2_source_code/README.md#setup), [5_working_prototype/README.md](5_working_prototype/README.md) |
| Test scripts | [4_sample_data_and_test_cases/README.md](4_sample_data_and_test_cases/README.md#test-cases) and the repository's `tests/` folder |
| Agent responsibilities | [ARCHITECTURE.md → Agent responsibilities](3_architecture_documentation/ARCHITECTURE.md#agent-responsibilities), [AGENTS.md](3_architecture_documentation/AGENTS.md) |
| Communication and interfaces | [ARCHITECTURE.md → Communication and interfaces](3_architecture_documentation/ARCHITECTURE.md#communication-and-interfaces), [PROTOCOL.md](3_architecture_documentation/PROTOCOL.md) |
| Orchestration | [ARCHITECTURE.md → Orchestration](3_architecture_documentation/ARCHITECTURE.md#orchestration), [ORCHESTRATION.md](3_architecture_documentation/ORCHESTRATION.md) |
| Evidence correlation | [ARCHITECTURE.md → Evidence correlation and decisions](3_architecture_documentation/ARCHITECTURE.md#evidence-correlation-and-decisions), [SCORING.md](3_architecture_documentation/SCORING.md) |
| Error handling | [ARCHITECTURE.md → Error handling](3_architecture_documentation/ARCHITECTURE.md#error-handling) |
| Overall workflow | [ARCHITECTURE.md → Overall workflow](3_architecture_documentation/ARCHITECTURE.md#overall-workflow-telemetry--agents--diagnosis--report) |
| Normal network operation sample | [sample_data/normal__…](4_sample_data_and_test_cases/sample_data/) |
| Multiple fault scenarios | 8 fault samples in [sample_data/](4_sample_data_and_test_cases/sample_data/) |
| Demo: end-to-end diagnosis, inter-agent communication, final report | [1_demo_video/](1_demo_video/) |
| Runnable prototype: CLI or dashboard | both: [5_working_prototype/](5_working_prototype/) |
| Telemetry → agents → diagnosis → report | [5_working_prototype/README.md](5_working_prototype/README.md#the-complete-workflow) and the video |

## Quick start (from the repository root)

```bash
pip install -e ".[dev]"
```

```bash
netcoop serve
```

Then open http://127.0.0.1:8765/, pick a sample and press **Diagnose**.

---

The documents and samples here are copies taken at commit `8644b74`. The repository itself, at
https://github.com/suvronilchatterjee7-create/netcoop-ai, is the authoritative version.
