# Source code

- **Live repository:** https://github.com/suvronilchatterjee7-create/netcoop-ai. The whole
  repository is the source deliverable.
- **Snapshot:** [`netcoop-ai-source.zip`](netcoop-ai-source.zip) is the complete source, made
  with `git archive`. It covers everything in the repository except this `deliverables/` folder.
  Unzip it and follow the setup below.

## What's inside

| path | contents |
|---|---|
| `netcoop/` | the implementation (see below) |
| `generator/` | the synthetic telemetry generator |
| `config/` | justified parameters, the agent and fault catalogue, the fitted model and baselines |
| `data/` | controlled vocabulary, format mappings, the nine labelled sample runs |
| `tests/` | 246 tests (pytest) |
| `docs/` | architecture, protocol, scoring, evaluation and decision documents |
| `pyproject.toml` | package metadata and **dependencies** |
| `Makefile`, `.github/workflows/ci.yml` | common commands; CI on every push |

The implementation in `netcoop/` is made up of:
- the protocol
- the Translator
- the case board and orchestrator
- the agents
- correlation
- the courtroom
- reporting
- the evaluation
- the dashboard
- the CLI

## Dependencies

- **Runtime:** Python 3.11+, pydantic, PyYAML, networkx, NumPy, pandas, Pint.
- **Development** (the `dev` extra): pytest, pytest-cov, Hypothesis, ruff, mypy, types-PyYAML,
  and the MCP SDK.
- **Dashboard:** no extra dependencies. It uses Python's standard library and ships its own fonts.

## Setup

```bash
python -m venv .venv
```

Activate the environment (`.venv\Scripts\activate` on Windows), then:

```bash
pip install -e ".[dev]"
```

```bash
pytest
```

```bash
netcoop serve
```
