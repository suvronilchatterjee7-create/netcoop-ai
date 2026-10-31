"""Human-in-the-loop review of recommended actions (light HITL, Phase 9).

Recommendations are for human review only; nothing is executed. A reviewer approves or rejects
each action. Every decision becomes an ACK message from ``human.<reviewer>`` whose causation is
the REPORT, appended to the run's trace. The trace hash in the manifest is updated, so
``netcoop replay`` still verifies the whole history, including who decided what.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from netcoop.orchestrator.trace import MANIFEST, TRACE, replay, trace_line
from netcoop.protocol.common import MessageType
from netcoop.protocol.messages import make_message
from netcoop.protocol.payloads import AckPayload, AckStatus, ReportPayload


@dataclass(frozen=True)
class Decision:
    action_index: int  # 1-based, as printed in report.md
    approve: bool
    note: str = ""


def reviewer_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9_.-]+", "-", name.strip().lower()).strip("-") or "anonymous"
    return f"human.{slug}"


def actions(run_dir: Path) -> list[str]:
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    return list(report["recommended_actions"])


def review(run_dir: Path, decisions: list[Decision], reviewer: str) -> list[dict[str, object]]:
    """Record decisions in the trace and manifest; returns the recorded entries."""
    board = replay(run_dir / TRACE)
    reports = board.query(type=MessageType.REPORT)
    if not reports:
        raise ValueError("run has no REPORT to review (paused or failed run?)")
    report_msg = reports[-1]
    assert isinstance(report_msg.payload, ReportPayload)
    acts = list(report_msg.payload.report.recommended_actions)
    last_round = max(e.round for e in board.entries())
    sender = reviewer_id(reviewer)
    recorded = []
    with (run_dir / TRACE).open("a", encoding="utf-8", newline="\n") as fh:
        for d in decisions:
            if not 1 <= d.action_index <= len(acts):
                raise ValueError(f"action {d.action_index} does not exist (1..{len(acts)})")
            reason = f"action {d.action_index}: {acts[d.action_index - 1]}" + (
                f" | note: {d.note}" if d.note else ""
            )
            msg = make_message(
                MessageType.ACK,
                sender=sender,
                correlation_id=board.incident_id,
                payload=AckPayload(
                    acked_msg_id=report_msg.msg_id,
                    status=AckStatus.ACCEPTED if d.approve else AckStatus.REJECTED,
                    reason=reason,
                ),
                timestamp=report_msg.timestamp,
                parent=report_msg,
            )
            status, _ = board.post(msg, last_round + 1, budgeted=False)
            if status.value != "accepted":
                continue  # identical decision already recorded: idempotent
            fh.write(trace_line(board.entries(board.version - 1)[0]) + "\n")
            recorded.append(
                {
                    "action": d.action_index,
                    "approved": d.approve,
                    "note": d.note,
                    "reviewer": sender,
                    "msg_id": msg.msg_id,
                }
            )
    manifest_path = run_dir / MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["trace_sha256"] = hashlib.sha256((run_dir / TRACE).read_bytes()).hexdigest()
    manifest["reviews"] = [*manifest.get("reviews", []), *recorded]
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    md = run_dir / "report.md"
    if md.is_file() and recorded:
        lines = (
            ["", "## Human review", ""]
            if "## Human review" not in md.read_text(encoding="utf-8")
            else []
        )
        lines += [
            f"- Action {r['action']}: **{'approved' if r['approved'] else 'rejected'}** "
            f"by {r['reviewer']}" + (f" ({r['note']})" if r["note"] else "")
            for r in recorded
        ]
        with md.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return recorded
