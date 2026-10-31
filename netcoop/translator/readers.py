"""Syntactic layer: read CSV / JSON / JSONL into tables of raw records, never raising.

Format is chosen by extension and, for unknown extensions, by sniffing the first
non-blank character. Parse failures become issues; partially readable files keep
their good records.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from netcoop.protocol.common import ErrorCode, Severity
from netcoop.translator.issues import IssueLog

Record = dict[str, Any]


@dataclass
class RawTable:
    """Records read from one file (or one list inside a JSON document)."""

    source: str
    fmt: str
    records: list[tuple[str, Record]] = field(default_factory=list)  # (locator, record)
    document: dict[str, Any] | None = None  # whole JSON object, for topology documents
    section: str | None = None  # list key inside a JSON document


def _decode(path: Path, log: IssueLog) -> str | None:
    try:
        return path.read_bytes().decode("utf-8-sig")
    except OSError as exc:
        log.add(ErrorCode.MALFORMED_INPUT, Severity.FATAL, path.name, f"cannot read file: {exc}")
    except UnicodeDecodeError as exc:
        log.add(ErrorCode.MALFORMED_INPUT, Severity.FATAL, path.name, f"not UTF-8 text: {exc}")
    return None


def _sniff(text: str) -> str:
    head = text.lstrip()[:1]
    if head == "[":
        return "json"
    if head == "{":
        first = text.lstrip().splitlines()[0].strip()
        try:
            json.loads(first)
            return "jsonl" if len(text.strip().splitlines()) > 1 else "json"
        except json.JSONDecodeError:
            return "json"
    return "csv"


def _read_csv(name: str, text: str, log: IssueLog) -> list[RawTable]:
    table = RawTable(name, "csv")
    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            log.add(ErrorCode.MALFORMED_INPUT, Severity.FATAL, name, "CSV has no header row")
            return []
        for i, row in enumerate(reader, start=2):
            if None in row:  # more cells than header columns
                log.add(
                    ErrorCode.MALFORMED_INPUT,
                    Severity.RECOVERABLE,
                    name,
                    "row has more cells than the header; extra cells ignored",
                    locator=f"row:{i}",
                )
                row.pop(None, None)
            # empty cell = missing value
            table.records.append(
                (f"row:{i}", {k: v for k, v in row.items() if v not in ("", None)})
            )
    except csv.Error as exc:
        log.add(ErrorCode.MALFORMED_INPUT, Severity.FATAL, name, f"CSV parse error: {exc}")
    return [table]


def _read_jsonl(name: str, text: str, log: IssueLog) -> list[RawTable]:
    table = RawTable(name, "jsonl")
    for i, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            log.add(
                ErrorCode.MALFORMED_INPUT,
                Severity.RECOVERABLE,
                name,
                f"unparseable JSON line skipped ({exc.msg})",
                locator=f"line:{i}",
            )
            continue
        if not isinstance(rec, dict):
            log.add(
                ErrorCode.MALFORMED_INPUT,
                Severity.RECOVERABLE,
                name,
                "JSON line is not an object; skipped",
                locator=f"line:{i}",
            )
            continue
        table.records.append((f"line:{i}", rec))
    return [table]


def _read_json(name: str, text: str, log: IssueLog) -> list[RawTable]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        log.add(
            ErrorCode.MALFORMED_INPUT,
            Severity.FATAL,
            name,
            f"invalid JSON: {exc.msg} at line {exc.lineno}",
        )
        return []
    if isinstance(data, list):
        t = RawTable(name, "json")
        t.records = [(f"index:{i}", r) for i, r in enumerate(data) if isinstance(r, dict)]
        return [t]
    if isinstance(data, dict):
        tables = []
        for key, val in data.items():
            if isinstance(val, list) and val and all(isinstance(r, dict) for r in val):
                t = RawTable(name, "json", document=data, section=key)
                t.records = [(f"{key}[{i}]", r) for i, r in enumerate(val)]
                tables.append(t)
        if tables:
            return tables
        return [RawTable(name, "json", records=[("root", data)], document=data)]
    log.add(
        ErrorCode.MALFORMED_INPUT,
        Severity.FATAL,
        name,
        "JSON document is neither an object nor a list",
    )
    return []


READERS = {"csv": _read_csv, "jsonl": _read_jsonl, "ndjson": _read_jsonl, "json": _read_json}


def read_path(path: Path, log: IssueLog) -> list[RawTable]:
    text = _decode(path, log)
    if text is None:
        return []
    if not text.strip():
        log.add(ErrorCode.MALFORMED_INPUT, Severity.FATAL, path.name, "file is empty")
        return []
    fmt = path.suffix.lower().lstrip(".")
    if fmt not in READERS:
        fmt = _sniff(text)
    return READERS[fmt](path.name, text, log)


def parse_timestamp(value: Any, epoch_ms_threshold: float) -> datetime | None:
    """ISO-8601 string or epoch seconds/milliseconds -> aware UTC datetime; None if unparseable.

    Naive ISO timestamps are taken as UTC (the issue is recorded by the caller).
    """
    if isinstance(value, bool):
        return None
    num: float | None = None
    if isinstance(value, int | float):
        num = float(value)
    elif isinstance(value, str):
        s = value.strip()
        try:
            num = float(s)
        except ValueError:
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            except ValueError:
                return None
            return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    if num is None or num != num:  # NaN
        return None
    seconds = num / 1000.0 if abs(num) >= epoch_ms_threshold else num
    try:
        return datetime.fromtimestamp(seconds, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None
