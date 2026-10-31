"""Protocol versions, adapters between them, and version negotiation.

Versions
--------
* **1.0 "lite"**: minimal interchange profile for simple or external agents. Flat
  envelope (``id``, ``incident``, ``from``, ``to``, ``time``), five message types
  (OBSERVATION, CLUE, HYPOTHESIS, ERROR, ACK), confidence as a percentage, no
  provenance, data quality, causation or roles. Specified in docs/PROTOCOL.md §6.
* **2.0**: the full protocol implemented by ``netcoop.protocol.messages``.

Adapters are pure ``dict -> dict`` functions registered per (from, to) pair; ``convert``
chains them along the shortest path. Every conversion appends to ``adaptations`` and names
any field it could not carry, so lossy steps are visible in the trace and the report.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Sequence
from typing import Any

from netcoop.config import get_value, load_config
from netcoop.protocol.common import BOARD, PROTOCOL_NAME, PROTOCOL_VERSION, ErrorCode
from netcoop.protocol.messages import Envelope, parse_message
from netcoop.protocol.vocabulary import get_vocabulary

Wire = dict[str, Any]
Adapter = Callable[[Wire], Wire]

V1 = "1.0"
V2 = PROTOCOL_VERSION
V1_TYPES = frozenset({"OBSERVATION", "CLUE", "HYPOTHESIS", "ERROR", "ACK"})
QUALITY_UNKNOWN_V1 = "quality_unknown_v1"

_ADAPTERS: dict[tuple[str, str], Adapter] = {}


class VersionError(Exception):
    """A message cannot be converted; ``code`` is the ErrorCode to report."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


def adapter(src: str, dst: str) -> Callable[[Adapter], Adapter]:
    def register(fn: Adapter) -> Adapter:
        _ADAPTERS[(src, dst)] = fn
        return fn

    return register


def supported_versions() -> tuple[str, ...]:
    vs = {v for pair in _ADAPTERS for v in pair} | {V2}
    return tuple(sorted(vs, key=_vkey))


def _vkey(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError as exc:
        raise VersionError(ErrorCode.INCOMPATIBLE_VERSION, f"bad version string {v!r}") from exc


def detect_version(data: Wire) -> str:
    if data.get("protocol") != PROTOCOL_NAME:
        raise VersionError(
            ErrorCode.INCOMPATIBLE_SCHEMA,
            f"not a netcoop message: protocol={data.get('protocol')!r}",
        )
    version = data.get("protocol_version", data.get("version"))
    if not isinstance(version, str):
        raise VersionError(ErrorCode.MISSING_FIELD, "message has no protocol version")
    return version


def _path(src: str, dst: str) -> list[tuple[str, str]]:
    prev: dict[str, str | None] = {src: None}
    queue = deque([src])
    while queue:
        cur = queue.popleft()
        if cur == dst:
            steps: list[tuple[str, str]] = []
            while (p := prev[cur]) is not None:
                steps.append((p, cur))
                cur = p
            return steps[::-1]
        for a, b in _ADAPTERS:
            if a == cur and b not in prev:
                prev[b] = cur
                queue.append(b)
    raise VersionError(ErrorCode.INCOMPATIBLE_VERSION, f"no adapter path {src} -> {dst}")


def convert(data: Wire, target: str) -> Wire:
    """Convert a wire message to ``target`` version (no-op if already there)."""
    out = data
    for step in _path(detect_version(data), target):
        try:
            out = _ADAPTERS[step](out)
        except (KeyError, TypeError, ValueError) as exc:
            raise VersionError(
                ErrorCode.MALFORMED_INPUT,
                f"cannot convert {step[0]}->{step[1]}: missing/invalid {exc}",
            ) from exc
    return out


def upgrade(data: Wire) -> Envelope:
    """Accept a message in any supported version and return a validated 2.0 model."""
    return parse_message(convert(data, V2))


def negotiate(ours: Sequence[str], theirs: Sequence[str]) -> str:
    """Highest version both sides support."""
    common = set(ours) & set(theirs)
    if not common:
        raise VersionError(
            ErrorCode.INCOMPATIBLE_VERSION,
            f"no common protocol version: {sorted(ours)} vs {sorted(theirs)}",
        )
    return max(common, key=_vkey)


# ----------------------------------------------------------------------------- 1.0 -> 2.0
def _entity_v1_to_v2(e: Wire) -> Wire:
    return {"entity_id": e["id"], "entity_type": e["type"]}


def _entity_v2_to_v1(e: Wire) -> Wire:
    return {"id": e["entity_id"], "type": e["entity_type"]}


def _assumed_quality() -> float:
    return float(get_value(load_config("protocol"), "v1_upgrade.assumed_data_quality"))


def _quality_v1() -> Wire:
    q = _assumed_quality()
    return {
        "score": q,
        "completeness": q,
        "freshness": q,
        "plausibility": q,
        "mapping_certainty": q,
        "issues": [QUALITY_UNKNOWN_V1],
    }


@adapter(V1, V2)
def _v1_to_v2(d: Wire) -> Wire:
    t = d.get("type")
    if t not in V1_TYPES:
        raise VersionError(ErrorCode.UNSUPPORTED_MESSAGE_TYPE, f"type {t!r} does not exist in 1.0")
    p = d["payload"]
    notes = [f"{V1}->{V2}"]
    payload: Wire
    if t == "OBSERVATION":
        payload = {
            "entity": _entity_v1_to_v2(p["entity"]),
            "metric": p["metric"],
            "unit": p["unit"],
            "points": [{"t": ts, "v": v} for ts, v in p["samples"]],
            "quality": _quality_v1(),
        }
        notes.append("assumed:quality")
    elif t == "CLUE":
        start, end = p["window"]
        payload = {
            "entity": _entity_v1_to_v2(p["entity"]),
            "metric": p["metric"],
            "statistic": "unspecified",
            "value": p["value"],
            "unit": p["unit"],
            "comparison": {
                "basis": "threshold",
                "reference_value": p.get("threshold"),
                "config_key": f"external:v{V1}",
                "method": "external",
            },
            "direction": p["direction"],
            "deviation": p["deviation"],
            "deviation_unit": "unspecified",
            "significant": p["significant"],
            "window": {"start": start, "end": end},
            "source_observation_ids": p["observations"],
            "data_quality": _assumed_quality(),
        }
        notes += ["assumed:data_quality", "unknown:statistic,persistence"]
    elif t == "HYPOTHESIS":
        payload = {
            "hypothesis_type": p["hypothesis"],
            "entities": [{"entity": _entity_v1_to_v2(e), "role": "root"} for e in p["entities"]],
            "local_confidence": p["confidence_pct"] / 100.0,
            "confidence_method": f"external:v{V1}",
            "supporting_clue_ids": p.get("supporting", []),
            "contradicting_clue_ids": p.get("contradicting", []),
        }
        notes.append("assumed:entity_roles=root")
    elif t == "ERROR":
        payload = {
            "code": p["code"],
            "severity": "fatal" if p.get("fatal") else "recoverable",
            "message": p["message"],
        }
    else:  # ACK
        payload = {"acked_msg_id": p["ack"], "status": p["status"]}
    return {
        "protocol": PROTOCOL_NAME,
        "protocol_version": V2,
        "schema_version": get_vocabulary().version,
        "msg_id": d["id"],
        "correlation_id": d["incident"],
        "sender": d["from"],
        "recipient": d.get("to") or BOARD,
        "timestamp": d["time"],
        "type": t,
        "payload": payload,
        "adaptations": [*d.get("adaptations", []), *notes],
    }


# ----------------------------------------------------------------------------- 2.0 -> 1.0
@adapter(V2, V1)
def _v2_to_v1(d: Wire) -> Wire:
    t = d.get("type")
    if t not in V1_TYPES:
        raise VersionError(
            ErrorCode.UNSUPPORTED_MESSAGE_TYPE, f"type {t!r} cannot be expressed in 1.0"
        )
    p = d["payload"]
    lost: list[str] = ["causation_id", "depth", "schema_version"]
    payload: Wire
    if t == "OBSERVATION":
        payload = {
            "entity": _entity_v2_to_v1(p["entity"]),
            "metric": p["metric"],
            "unit": p["unit"],
            "samples": [[pt["t"], pt["v"]] for pt in p["points"]],
        }
        lost += ["observed_from", "sources", "quality"]
    elif t == "CLUE":
        payload = {
            "entity": _entity_v2_to_v1(p["entity"]),
            "metric": p["metric"],
            "unit": p["unit"],
            "value": p["value"],
            "threshold": p["comparison"].get("reference_value"),
            "direction": p["direction"],
            "deviation": p["deviation"],
            "significant": p["significant"],
            "window": [p["window"]["start"], p["window"]["end"]],
            "observations": p["source_observation_ids"],
        }
        lost += ["statistic", "comparison.basis/method/config_key", "persistence", "data_quality"]
    elif t == "HYPOTHESIS":
        payload = {
            "hypothesis": p["hypothesis_type"],
            "entities": [_entity_v2_to_v1(he["entity"]) for he in p["entities"]],
            "confidence_pct": p["local_confidence"] * 100.0,
            "supporting": p.get("supporting_clue_ids", []),
            "contradicting": p.get("contradicting_clue_ids", []),
        }
        lost += ["entity roles", "confidence_method"]
    elif t == "ERROR":
        payload = {"code": p["code"], "message": p["message"], "fatal": p["severity"] == "fatal"}
        lost += ["severity(warning)", "related_msg_id", "source", "context"]
    else:  # ACK
        payload = {"ack": p["acked_msg_id"], "status": p["status"]}
        lost.append("reason")
    return {
        "protocol": PROTOCOL_NAME,
        "version": V1,
        "id": d["msg_id"],
        "incident": d["correlation_id"],
        "from": d["sender"],
        "to": d.get("recipient", BOARD),
        "time": d["timestamp"],
        "type": t,
        "payload": payload,
        "adaptations": [*d.get("adaptations", []), f"{V2}->{V1}", "lossy:" + ",".join(lost)],
    }
