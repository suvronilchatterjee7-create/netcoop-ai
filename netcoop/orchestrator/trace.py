"""Run traces: every accepted board message, in order, as JSON lines; plus replay.

``runs/<incident_id>/trace.jsonl`` holds one ``{"seq", "round", "msg"}`` object per line,
written as each message is committed (so a dashboard can tail it). ``manifest.json``
records hashes of input, config and trace for reproducibility. ``replay`` rebuilds the
board from a trace and checks it is byte-for-byte the same run.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import IO, Any

from netcoop import __version__
from netcoop.board.board import Board, Entry
from netcoop.config import get_value, load_config
from netcoop.generation import LABEL_FILES
from netcoop.protocol.messages import dump_message, parse_message
from netcoop.protocol.payloads import AckStatus

TRACE = "trace.jsonl"
MANIFEST = "manifest.json"


def trace_line(entry: Entry) -> str:
    return json.dumps(
        {"seq": entry.seq, "round": entry.round, "msg": dump_message(entry.msg)},
        sort_keys=True,
        separators=(",", ":"),
    )


class TraceWriter:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._fh: IO[str] = path.open("w", encoding="utf-8", newline="\n")
        self._hash = hashlib.sha256()

    def __call__(self, entry: Entry) -> None:
        line = trace_line(entry) + "\n"
        self._fh.write(line)
        self._hash.update(line.encode())

    def close(self) -> str:
        self._fh.close()
        return self._hash.hexdigest()


def input_files(inputs: Path | list[Path]) -> list[Path]:
    paths = [inputs] if isinstance(inputs, Path) else list(inputs)
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.is_file() and f.name not in LABEL_FILES)
        elif p.is_file():
            files.append(p)
    return files


def input_hash(inputs: Path | list[Path]) -> str:
    h = hashlib.sha256()
    for f in input_files(inputs):
        h.update(f.name.encode())
        h.update(hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()


def code_version() -> str:
    try:
        rev = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
            timeout=5,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        rev = ""
    return f"{__version__}+{rev}" if rev else __version__


def run_seed() -> int:
    return int(get_value(load_config("generation"), "sweep.base_seed"))


def write_manifest(run_dir: Path, data: dict[str, Any]) -> Path:
    path = run_dir / MANIFEST
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return path


class ReplayError(Exception):
    pass


def replay(trace_path: Path) -> Board:
    """Rebuild the board from a trace; raises ReplayError if the trace is not a valid run."""
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ReplayError("empty trace")
    first = json.loads(lines[0])
    cfg = load_config("orchestrator")
    board = Board(
        first["msg"]["correlation_id"],
        int(get_value(cfg, "board.max_causation_depth")),
        int(get_value(cfg, "board.per_agent_round_budget")),
    )
    h = hashlib.sha256()
    for i, line in enumerate(lines):
        rec = json.loads(line)
        if rec["seq"] != i:
            raise ReplayError(f"line {i + 1}: sequence {rec['seq']} out of order")
        msg = parse_message(rec["msg"])
        status, reason = board.post(
            msg, rec["round"], budgeted=False
        )  # trace holds accepted posts only
        if status is not AckStatus.ACCEPTED:
            raise ReplayError(f"line {i + 1}: {msg.msg_id} {status.value}: {reason}")
        if trace_line(board.entries(i)[0]) != line:
            raise ReplayError(f"line {i + 1}: re-serialised message differs from trace")
        h.update((line + "\n").encode())
    manifest = trace_path.with_name(MANIFEST)
    if manifest.is_file():
        expected = json.loads(manifest.read_text(encoding="utf-8")).get("trace_sha256")
        if expected and expected != h.hexdigest():
            raise ReplayError("trace hash does not match manifest")
    return board
