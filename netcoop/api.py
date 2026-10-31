"""Public programmatic API (stable entry point for the CLI and a future dashboard).

    from netcoop.api import diagnose
    report = diagnose(Path("data/generated/weak_wifi/<run>"))

``run_diagnosis`` returns the full ``RunResult`` (board, trace location, manifest) and
accepts an ``on_event`` hook that receives every board message and stage transition live.
"""

from __future__ import annotations

from pathlib import Path

from netcoop.orchestrator.orchestrator import Event, EventHook, Orchestrator, RunResult
from netcoop.protocol.report import Report

DEFAULT_RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"


def run_diagnosis(
    inputs: Path | list[Path],
    *,
    incident_id: str | None = None,
    out_dir: Path | None = DEFAULT_RUNS_DIR,
    on_event: EventHook | None = None,
    orchestrator: Orchestrator | None = None,
) -> RunResult:
    """Run the full pipeline. ``out_dir=None`` keeps everything in memory (no trace files)."""
    return (orchestrator or Orchestrator()).run(
        inputs, incident_id=incident_id, out_dir=out_dir, on_event=on_event
    )


def diagnose(inputs: Path | list[Path], **kwargs: object) -> Report:
    """Diagnose telemetry files or a run directory and return the unified report."""
    return run_diagnosis(inputs, **kwargs).report  # type: ignore[arg-type]


__all__ = ["Event", "EventHook", "RunResult", "diagnose", "run_diagnosis"]
