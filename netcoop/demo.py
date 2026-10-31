"""Scripted walkthrough for the demo video (``netcoop demo``, docs/DEMO_SCRIPT.md).

Scenes come from config/demo.yaml and run on the committed samples in data/samples/. Each
scene checks the report status against its ``expect`` so a changed outcome shows up during
rehearsal rather than on camera.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from netcoop.config import get_value, load_config

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLES = REPO_ROOT / "data" / "samples"
EVALUATION_MD = REPO_ROOT / "docs" / "EVALUATION.md"

Write = Callable[[str], None]


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _trace(messages: list[tuple[int, int, Any]], write: Write) -> None:
    max_lines = int(get_value(load_config("demo"), "trace.max_lines"))
    cards = [m.sender for _, _, m in messages if m.type.value == "CAPABILITY"]
    write(f"  {len(cards)} capability cards: {', '.join(cards)}")
    counted = {"OBSERVATION", "CLUE", "CAPABILITY"}
    tally = Counter(
        (m.type.value, m.sender) for _, _, m in messages if m.type.value in counted - {"CAPABILITY"}
    )
    for (kind, sender), n in sorted(tally.items()):
        write(f"  {n:5d} x {kind:11s} from {sender}")
    chain = [(s, r, m) for s, r, m in messages if m.type.value not in counted]
    write(f"  decision chain ({len(chain)} messages):")
    for seq, rnd, m in chain[:max_lines]:
        cause = f"  <- {m.causation_id}" if m.causation_id else ""
        write(
            f"  r{rnd} #{seq:<5} {m.type.value:11s} {m.sender:>16s} -> {m.recipient:<14s}"
            f" {m.msg_id}{cause}"
        )
    if len(chain) > max_lines:
        write(f"  ... {len(chain) - max_lines} more (netcoop run -v shows all)")


def _translator(sample: Path, write: Write) -> None:
    from netcoop.translator.translator import Translator

    result = Translator().translate(sample, sample.name)
    write(f"  dialects: {result.dialects}")
    write(f"  stats:    {result.stats}")
    codes = Counter(f"{e.severity.value} {e.code.value}" for e in result.errors)
    for code, n in sorted(codes.items()):
        write(f"  {n:4d} x {code}")


def _report(report: Any, write: Write) -> None:
    cfg = load_config("demo")
    x = report.x_netcoop
    cat = x.confidence_category if x else "-"
    write(f"  status:      {report.status.value}")
    write(f"  root cause:  {report.suspected_root_cause}")
    write(f"  confidence:  {report.confidence:.2f} ({cat})")
    if report.affected_devices:
        write(f"  affected:    {', '.join(report.affected_devices)}")
    for e in report.supporting_evidence[: int(get_value(cfg, "report.max_evidence"))]:
        write(f"  evidence:    {e.interpretation}")
    for a in report.recommended_actions[: int(get_value(cfg, "report.max_actions"))]:
        write(f"  action:      {a}")
    if report.alternative_causes:
        write(f"  alternatives: {'; '.join(report.alternative_causes)}")


def _abstention(report: Any, write: Write) -> None:
    x = report.x_netcoop
    for m in x.missing_evidence if x else ():
        write(f"  would resolve it: {m}")
    for lim in report.limitations:
        write(f"  limitation:  {lim}")


def _courtroom(report: Any, write: Write) -> None:
    c = report.x_netcoop.courtroom if report.x_netcoop else None
    if c is None or not c.invoked:
        write("  courtroom not invoked")
        return
    write(f"  contenders:  {' vs '.join(c.contenders)}")
    write(f"  rounds:      {c.rounds}   outcome: {c.outcome}")
    for part in c.summary.split(" | "):
        write(f"  ruling:      {part}")
    write(f"  transcript:  {', '.join(c.transcript_msg_ids)}")


def _replay(run_dir: Path | None, write: Write) -> None:
    from netcoop.orchestrator.trace import replay

    if run_dir is None:
        write("  (no trace written)")
        return
    board = replay(run_dir / "trace.jsonl")
    write(f"  replayed {board.version} messages from {_rel(run_dir)}/trace.jsonl: trace verified")


def _metrics(write: Write) -> None:
    if not EVALUATION_MD.is_file():
        write("  docs/EVALUATION.md missing: run `netcoop eval`")
        return
    lines = EVALUATION_MD.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("## Headline"))
    for ln in lines[start + 1 :]:
        if ln.startswith("## "):
            break
        if ln.startswith("|") and not ln.startswith("|---"):
            cells = [c.strip().replace("**", "") for c in ln.strip("|").split("|")]
            write(f"  {cells[0]:<74s} {cells[1]}")


def run_demo(
    only: list[int] | None = None,
    out_dir: Path | None = REPO_ROOT / "runs" / "demo",
    pause: Callable[[], None] | None = None,
    write: Write = print,
) -> int:
    """Play the scenes (1-based ``only`` selects some); returns the number of unmet expectations."""
    from netcoop.api import run_diagnosis
    from netcoop.orchestrator.orchestrator import Event

    scenes: list[dict[str, Any]] = get_value(load_config("demo"), "scenes")
    mismatches = 0
    for i, scene in enumerate(scenes, 1):
        if only and i not in only:
            continue
        write("")
        write(f"=== Scene {i}/{len(scenes)}: {scene['title']} ===")
        write(" ".join(scene["narration"].split()))
        show: list[str] = scene["show"]
        if not scene["sample"]:
            if "metrics" in show:
                _metrics(write)
        else:
            sample = SAMPLES / scene["sample"]
            write(f"$ netcoop run data/samples/{scene['sample']}")
            events: list[Any] = []
            result = run_diagnosis(sample, out_dir=out_dir, on_event=events.append)
            messages = [
                (e.data["seq"], e.round, e.data["msg"])
                for e in events
                if isinstance(e, Event) and e.kind == "message"
            ]
            report = result.report
            assert report is not None
            for part in show:
                write(f"-- {part}")
                if part == "trace":
                    _trace(messages, write)
                elif part == "translator":
                    _translator(sample, write)
                elif part == "report":
                    _report(report, write)
                elif part == "abstention":
                    _abstention(report, write)
                elif part == "courtroom":
                    _courtroom(report, write)
                elif part == "replay":
                    _replay(result.run_dir, write)
            if result.run_dir:
                write(f"  full report: {_rel(result.run_dir / 'report.md')}")
            if scene["expect"] and report.status.value != scene["expect"]:
                mismatches += 1
                write(f"  !! expected status {scene['expect']}, got {report.status.value}")
        if pause:
            pause()
    return mismatches


__all__ = ["run_demo"]
