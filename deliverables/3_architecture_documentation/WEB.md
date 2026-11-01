# Local dashboard

```bash
netcoop serve                 # opens http://127.0.0.1:8765/ in your browser
netcoop serve --port 9000 --no-browser
```

A local web page for running and reading diagnoses. It needs nothing beyond the normal install:
the server is Python's standard library and the page is plain HTML, CSS and JavaScript
(`netcoop/web/`). Stop it with Ctrl+C.

## What you can do

- **Diagnose.** Pick a sample in the left rail, or a folder from `data/test`, `data/ambiguity` or
  `data/generated` once they exist, then press **Diagnose**. Each folder shows the fault its
  generator injected; the agents never see that label.
- **Watch it happen.** Messages stream from the orchestrator as they are committed. Fig. 1 draws
  the decision chain:
  - one lane per agent, rounds left to right, numbered points for messages
  - lines from each message to the one that caused it
  - observations, clues and capability cards are counted rather than drawn
  - the chain is paced (`config/web.yaml` `replay.step_ms`) so it can be followed on a screen
    recording
- **Read the report.** It is laid out like a research paper:
  - the root cause as the title and an abstract of how the agents got there
  - evidence, recommended actions, what would settle an abstention, affected devices
  - the courtroom ruling, alternatives, data quality and the itemised score
  - a reference list of every cited message
- **Follow a citation.** Every red number cites a board message.
  - Hover or focus it to highlight the message in Fig. 1 and read it.
  - Click it to jump to its reference.
  - Click a point in Fig. 1 to jump to the claim that cites it.
- **Past runs.** Every dashboard diagnosis is written to `runs/web/<incident>/`, with the same
  report, trace and manifest as `netcoop run`. The Past runs tab lists them, and
  `#run=<incident>` in the URL opens one directly.
- **Evaluation.** The headline table from `docs/EVALUATION.md`.

## API

| endpoint | returns |
|---|---|
| `GET /api/inputs` | run folders by collection (samples in full, others up to `inputs.max_listed`) |
| `GET /api/diagnose?input=<id>` | Server-Sent Events: `start`, one `message` per board message, then `done` (with the incident id) or `failed` |
| `GET /api/runs` | past dashboard runs, newest first |
| `GET /api/runs/<incident>` | report, manifest, decision chain, counts, and the clues and observations the evidence cites |
| `GET /api/evaluation` | headline metric rows |
| `GET /api/config` | the replay pace |

## Safety

The server has no authentication. It therefore:

- binds to 127.0.0.1 only
- diagnoses only folders under the roots listed in `config/web.yaml` `inputs.roots`
- serves files from `netcoop/web/static/` only

Anything else returns 404, and `tests/test_web.py` checks these limits. Recommended actions are
shown for human review; nothing is executed.
