"""Aggregated issue log: many identical record-level problems become one typed ERROR."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

from netcoop.protocol.common import ErrorCode, Severity, SourceRef
from netcoop.protocol.payloads import ErrorPayload

_SEVERITY_ORDER = {Severity.WARNING: 0, Severity.RECOVERABLE: 1, Severity.FATAL: 2}


@dataclass
class Issue:
    code: ErrorCode
    severity: Severity
    source: str
    message: str
    field: str | None = None
    first_locator: str | None = None
    count: int = 0
    context: dict[str, Any] = dc_field(default_factory=dict)


class IssueLog:
    """Collects issues keyed by (code, source, field, message)."""

    def __init__(self) -> None:
        self._issues: dict[tuple[str, str, str | None, str], Issue] = {}

    def add(
        self,
        code: ErrorCode,
        severity: Severity,
        source: str,
        message: str,
        *,
        field: str | None = None,
        locator: str | None = None,
        **context: Any,
    ) -> None:
        key = (code.value, source, field, message)
        issue = self._issues.get(key)
        if issue is None:
            issue = self._issues[key] = Issue(code, severity, source, message, field, locator)
        issue.count += 1
        if _SEVERITY_ORDER[severity] > _SEVERITY_ORDER[issue.severity]:
            issue.severity = severity
        for k, v in context.items():
            issue.context.setdefault(k, v)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(
            sorted(
                self._issues.values(),
                key=lambda i: (i.source, i.code.value, i.field or "", i.message),
            )
        )

    def __len__(self) -> int:
        return len(self._issues)

    def codes(self) -> set[ErrorCode]:
        return {i.code for i in self._issues.values()}

    def for_source(self, source: str) -> list[Issue]:
        return [i for i in self if i.source == source]

    def to_payloads(self, dialects: dict[str, str]) -> list[ErrorPayload]:
        out = []
        for i in self:
            ctx: dict[str, str | float | int | bool] = {"count": i.count}
            if i.field:
                ctx["field"] = i.field
            for k, v in i.context.items():
                ctx[k] = v if isinstance(v, str | float | int | bool) else str(v)
            out.append(
                ErrorPayload(
                    code=i.code,
                    severity=i.severity,
                    message=i.message if i.count == 1 else f"{i.message} ({i.count} occurrences)",
                    source=SourceRef(
                        source=i.source,
                        dialect=dialects.get(i.source, "unrecognised"),
                        locator=i.first_locator or "file",
                        raw_field=i.field,
                    ),
                    context=ctx,
                )
            )
        return out
