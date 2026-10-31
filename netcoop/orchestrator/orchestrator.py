"""Orchestrator: ingestion -> collaboration rounds -> correlation -> reporting.

* **Ingestion (round 0):** capability cards, then the Translator's TOPOLOGY, OBSERVATIONs
  and ERRORs are posted.
* **Rounds 1..N:** each active agent receives the new messages its card subscribes to (plus
  messages addressed to it and REQUESTs it can serve). Agents in a round run concurrently,
  but their posts are committed in agent-id order, so the result does not depend on thread
  scheduling. Rounds repeat until no agent posts anything (convergence) or the round limit.
* **Isolation:** an agent that raises or exceeds its timeout is reported (AGENT_FAILURE /
  AGENT_TIMEOUT), its output for that round is discarded, and it is disabled; the run
  continues and the report lists the missing evidence.
* **Routing:** REQUESTs go to agents whose card can serve the capability. A REQUEST nobody
  can serve gets an ``unsupported`` RESPONSE from the orchestrator.
* **Closing stages:** correlator -> VERDICT, reporter -> REPORT.
"""

from __future__ import annotations

import concurrent.futures as cf
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from netcoop.agents.base import Agent, AgentContext
from netcoop.board.board import Board, message_metric
from netcoop.config import config_hash, get_value, load_config
from netcoop.orchestrator.stages import (
    Correlator,
    ProvisionalCorrelator,
    ProvisionalReporter,
    Reporter,
    RunInfo,
)
from netcoop.orchestrator.trace import (
    TRACE,
    TraceWriter,
    code_version,
    input_hash,
    run_seed,
    write_manifest,
)
from netcoop.protocol.capability import AgentRole, CapabilityCard
from netcoop.protocol.common import (
    BOARD,
    PROTOCOL_VERSION,
    ErrorCode,
    MessageType,
    ProtocolModel,
    Severity,
)
from netcoop.protocol.messages import Envelope, make_message
from netcoop.protocol.payloads import (
    CapabilityPayload,
    ErrorPayload,
    ReportPayload,
    RequestPayload,
    ResponsePayload,
    ResponseStatus,
)
from netcoop.protocol.report import Report, RunManifest
from netcoop.protocol.vocabulary import get_vocabulary
from netcoop.translator.translator import TranslationResult, Translator
from netcoop.translator.translator import capability_card as translator_card

ORCHESTRATOR_ID = "orchestrator"
ORCHESTRATOR_CARD = CapabilityCard(
    agent_id=ORCHESTRATOR_ID,
    version="0.1.0",
    role=AgentRole.EXTERNAL,
    description="Dispatches agents, routes requests, enforces budgets and reports agent failures.",
    protocol_versions=(PROTOCOL_VERSION,),
    consumes_types=(),
    produces_types=(MessageType.CAPABILITY, MessageType.ERROR, MessageType.RESPONSE),
)


@dataclass
class Event:
    """Progress event for UIs.

    kind: message, round_start, round_end, agent_failed, stage or done.
    """

    kind: str
    round: int
    data: dict[str, Any] = field(default_factory=dict)


EventHook = Callable[[Event], None]


@dataclass
class RunResult:
    report: Report
    board: Board
    info: RunInfo
    translation: TranslationResult
    run_dir: Path | None
    manifest: dict[str, Any]


class Orchestrator:
    def __init__(
        self,
        agents: list[Agent] | None = None,
        correlator: Correlator | None = None,
        reporter: Reporter | None = None,
        translator: Translator | None = None,
        *,
        timeout_s: float | None = None,
        max_rounds: int | None = None,
    ) -> None:
        cfg = load_config("orchestrator")
        if agents is None:
            from netcoop.agents.registry import create_agents

            agents = create_agents()
        self.agents = sorted(agents, key=lambda a: a.agent_id)
        ids = [a.agent_id for a in self.agents]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate agent ids: {ids}")
        self.correlator = correlator or ProvisionalCorrelator()
        self.reporter = reporter or ProvisionalReporter()
        self.translator = translator or Translator()
        self.max_rounds = max_rounds or int(get_value(cfg, "rounds.max_rounds"))
        self.max_depth = int(get_value(cfg, "board.max_causation_depth"))
        self.budget = int(get_value(cfg, "board.per_agent_round_budget"))
        self.timeout_s = timeout_s or float(get_value(cfg, "agents.timeout_s"))
        self.max_workers = int(get_value(cfg, "agents.max_workers"))

    # ------------------------------------------------------------------ public
    def run(
        self,
        inputs: Path | list[Path],
        incident_id: str | None = None,
        out_dir: Path | None = None,
        on_event: EventHook | None = None,
    ) -> RunResult:
        emit = on_event or (lambda _e: None)
        started = time.time()
        ihash = input_hash(inputs)
        incident = incident_id or f"inc-{ihash[:12]}"
        manifest = RunManifest(
            incident_id=incident,
            input_hash=ihash,
            config_hash=config_hash(),
            code_version=code_version(),
            protocol_version=PROTOCOL_VERSION,
            vocabulary_version=get_vocabulary().version,
            seed=run_seed(),
        )
        info = RunInfo(incident_id=incident, manifest=manifest)
        board = Board(incident, self.max_depth, self.budget)
        run_dir = out_dir / incident if out_dir is not None else None
        writer = TraceWriter(run_dir / TRACE) if run_dir is not None else None
        if writer is not None:
            board.subscribe(writer)
        current_round = [0]
        board.subscribe(
            lambda e: emit(Event("message", current_round[0], {"seq": e.seq, "msg": e.msg}))
        )

        translation = self.translator.translate(inputs, incident)
        now = translation.reference_time or datetime(1970, 1, 1, tzinfo=UTC)

        # ---- round 0: cards + ingestion
        emit(Event("round_start", 0))
        for card in [
            ORCHESTRATOR_CARD,
            translator_card(),
            *(a.card for a in self.agents),
            self.correlator.card,
            self.reporter.card,
        ]:
            self._post(
                board,
                self._msg(
                    MessageType.CAPABILITY,
                    card.agent_id,
                    incident,
                    CapabilityPayload(card=card),
                    now,
                ),
                0,
            )
        for m in translation.messages:  # ingestion is not subject to the per-agent flood budget
            self._post(board, m, 0, budgeted=False)
        active = self._negotiate_and_activate(board, translation, info, now)
        self._report_rejections(board, 0, incident, now)
        emit(Event("round_end", 0, {"posts": board.version}))

        # ---- collaboration rounds
        cursors = {a.agent_id: 0 for a in active}
        executor = cf.ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="agent")
        try:
            for a in active:
                a.start(AgentContext(a.agent_id, board, 0, now))
            for r in range(1, self.max_rounds + 1):
                current_round[0] = r
                info.rounds = r
                emit(Event("round_start", r))
                posted = self._round(r, active, cursors, board, executor, info, now, emit)
                emit(Event("round_end", r, {"posts": posted}))
                if posted == 0:
                    info.converged = True
                    break
            else:
                self._post(
                    board,
                    self._error(
                        incident,
                        now,
                        ErrorCode.BUDGET_EXCEEDED,
                        Severity.WARNING,
                        f"round limit {self.max_rounds} reached before convergence",
                    ),
                    r,
                )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        # ---- closing stages
        r_final = info.rounds + 1
        current_round[0] = r_final
        emit(Event("stage", r_final, {"stage": "correlation"}))
        verdict_payload = self.correlator.correlate(board, info)
        verdict = self._msg(
            MessageType.VERDICT, self.correlator.card.agent_id, incident, verdict_payload, now
        )
        self._post(board, verdict, r_final)
        emit(Event("stage", r_final, {"stage": "reporting"}))
        report = self.reporter.report(board, verdict, info)
        report_msg = make_message(
            MessageType.REPORT,
            sender=self.reporter.card.agent_id,
            correlation_id=incident,
            payload=ReportPayload(report=report),
            timestamp=now,
            parent=verdict,
        )
        self._post(board, report_msg, r_final)

        manifest_data: dict[str, Any] = {
            **manifest.model_dump(mode="json"),
            "rounds": info.rounds,
            "converged": info.converged,
            "agents": {a.agent_id: a.card.version for a in self.agents},
            "failed_agents": info.failed_agents,
            "inactive_agents": info.inactive_agents,
            "message_counts": board.counts(),
            "rejections": len(board.rejections),
            "timing": {"started_unix": started, "elapsed_s": round(time.time() - started, 3)},
        }
        if writer is not None and run_dir is not None:
            manifest_data["trace_sha256"] = writer.close()
            write_manifest(run_dir, manifest_data)
            (run_dir / "report.json").write_text(
                report.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
        emit(Event("done", r_final, {"status": report.status.value}))
        return RunResult(report, board, info, translation, run_dir, manifest_data)

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _msg(
        t: MessageType,
        sender: str,
        incident: str,
        payload: ProtocolModel,
        now: datetime,
        parent: Envelope | None = None,
        recipient: str = BOARD,
    ) -> Envelope:
        return make_message(
            t,
            sender=sender,
            correlation_id=incident,
            payload=payload,
            timestamp=now,
            parent=parent,
            recipient=recipient,
        )

    def _error(
        self,
        incident: str,
        now: datetime,
        code: ErrorCode,
        sev: Severity,
        text: str,
        parent: Envelope | None = None,
        **ctx: str | int,
    ) -> Envelope:
        return self._msg(
            MessageType.ERROR,
            ORCHESTRATOR_ID,
            incident,
            ErrorPayload(
                code=code,
                severity=sev,
                message=text,
                context=dict(ctx),
                related_msg_id=parent.msg_id if parent else None,
            ),
            now,
        )

    @staticmethod
    def _post(board: Board, msg: Envelope, r: int, *, budgeted: bool = True) -> bool:
        status, _ = board.post(msg, r, budgeted=budgeted)
        return status.value == "accepted"

    def _negotiate_and_activate(
        self, board: Board, tr: TranslationResult, info: RunInfo, now: datetime
    ) -> list[Agent]:
        observed = {o.metric for o in tr.observations}
        active: list[Agent] = []
        for a in self.agents:
            if PROTOCOL_VERSION not in a.card.protocol_versions:
                info.failed_agents[a.agent_id] = "incompatible protocol version"
                self._post(
                    board,
                    self._error(
                        info.incident_id,
                        now,
                        ErrorCode.INCOMPATIBLE_VERSION,
                        Severity.FATAL,
                        f"agent {a.agent_id} does not speak protocol {PROTOCOL_VERSION}",
                        agent=a.agent_id,
                    ),
                    0,
                )
            elif not a.card.is_active(observed):
                info.inactive_agents[a.agent_id] = a.card.optional
            else:
                active.append(a)
        return active

    def _deliverable(self, m: Envelope, agent: Agent) -> bool:
        if m.sender == agent.agent_id:
            return False
        if m.recipient == agent.agent_id:
            return True
        if m.recipient != BOARD:
            return False
        if m.type is MessageType.REQUEST:
            assert isinstance(m.payload, RequestPayload)
            return agent.card.can_serve(m.payload.capability)
        return agent.card.wants(m.type, message_metric(m))

    def _round(
        self,
        r: int,
        active: list[Agent],
        cursors: dict[str, int],
        board: Board,
        executor: cf.ThreadPoolExecutor,
        info: RunInfo,
        now: datetime,
        emit: EventHook,
    ) -> int:
        version_before = board.version
        jobs: dict[str, tuple[AgentContext, cf.Future[None]]] = {}
        for a in active:
            if a.agent_id in info.failed_agents:
                continue
            inbox = [
                e.msg for e in board.entries(cursors[a.agent_id]) if self._deliverable(e.msg, a)
            ]
            cursors[a.agent_id] = board.version
            if not inbox:
                continue
            ctx = AgentContext(a.agent_id, board, r, now)
            jobs[a.agent_id] = (ctx, executor.submit(a.step, inbox, ctx))

        deadline = time.monotonic() + self.timeout_s
        for agent_id in sorted(jobs):  # commit order = agent-id order (deterministic)
            ctx, fut = jobs[agent_id]
            try:
                fut.result(timeout=max(0.0, deadline - time.monotonic()))
            except cf.TimeoutError:
                self._fail(
                    agent_id,
                    ErrorCode.AGENT_TIMEOUT,
                    f"no result within {self.timeout_s:g} s",
                    board,
                    info,
                    now,
                    r,
                    emit,
                )
                continue
            except Exception as exc:  # noqa: BLE001 - isolation is the point
                self._fail(
                    agent_id,
                    ErrorCode.AGENT_FAILURE,
                    f"{type(exc).__name__}: {exc}",
                    board,
                    info,
                    now,
                    r,
                    emit,
                )
                continue
            for msg in ctx.outbox:
                if msg.sender != agent_id:
                    continue
                board.post(msg, r)
        self._report_rejections(board, r, info.incident_id, now)
        self._route_requests(board, version_before, active, info, now, r)
        return sum(1 for e in board.entries(version_before) if e.msg.sender != ORCHESTRATOR_ID)

    def _fail(
        self,
        agent_id: str,
        code: ErrorCode,
        reason: str,
        board: Board,
        info: RunInfo,
        now: datetime,
        r: int,
        emit: EventHook,
    ) -> None:
        info.failed_agents[agent_id] = reason
        self._post(
            board,
            self._error(
                info.incident_id,
                now,
                code,
                Severity.FATAL,
                f"agent {agent_id} disabled: {reason}",
                agent=agent_id,
                round=r,
            ),
            r,
        )
        emit(Event("agent_failed", r, {"agent": agent_id, "reason": reason}))

    def _report_rejections(self, board: Board, r: int, incident: str, now: datetime) -> None:
        counts: Counter[tuple[str, str]] = Counter(
            (rej.msg.sender, rej.reason.split(" ", 1)[0])
            for rej in board.rejections
            if rej.round == r
        )
        for (sender, kind), n in sorted(counts.items()):
            example = next(
                rej.reason
                for rej in board.rejections
                if rej.round == r and rej.msg.sender == sender and rej.reason.startswith(kind)
            )
            self._post(
                board,
                self._error(
                    incident,
                    now,
                    ErrorCode.BUDGET_EXCEEDED,
                    Severity.WARNING,
                    f"{n} posts from {sender} rejected by the board: {example}",
                    agent=sender,
                    count=n,
                    round=r,
                ),
                r,
            )

    def _route_requests(
        self, board: Board, since: int, active: list[Agent], info: RunInfo, now: datetime, r: int
    ) -> None:
        alive = {a.agent_id: a for a in active if a.agent_id not in info.failed_agents}
        for e in board.entries(since):
            m = e.msg
            if m.type is not MessageType.REQUEST:
                continue
            assert isinstance(m.payload, RequestPayload)
            if m.recipient == BOARD:
                servable = any(
                    a.card.can_serve(m.payload.capability)
                    for aid, a in alive.items()
                    if aid != m.sender
                )
            else:
                servable = m.recipient in alive
            if not servable:
                resp = ResponsePayload(
                    request_msg_id=m.msg_id,
                    status=ResponseStatus.UNSUPPORTED,
                    detail=f"no active agent serves {m.payload.capability}",
                )
                self._post(
                    board,
                    self._msg(
                        MessageType.RESPONSE,
                        ORCHESTRATOR_ID,
                        info.incident_id,
                        resp,
                        now,
                        parent=m,
                        recipient=m.sender,
                    ),
                    r,
                )
