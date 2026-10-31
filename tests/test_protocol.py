"""Phase 1 tests: vocabulary, message models, round trips, validation, versions, docs."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, ValidationError

from netcoop.config import get_value, load_config
from netcoop.protocol import schema_export
from netcoop.protocol.common import ErrorCode, MessageType
from netcoop.protocol.messages import (
    MESSAGE_CLASSES,
    content_id,
    dump_message,
    make_message,
    parse_message,
    to_json,
)
from netcoop.protocol.payloads import HypothesisPayload, ObservationPayload, Point
from netcoop.protocol.report import Report
from netcoop.protocol.versioning import (
    V1,
    V1_TYPES,
    V2,
    VersionError,
    convert,
    negotiate,
    supported_versions,
    upgrade,
)
from netcoop.protocol.vocabulary import get_vocabulary
from tests import protocol_factories as pf

ALL_TYPES = list(MessageType)


# ----------------------------------------------------------------------------- vocabulary
def test_vocabulary_has_first_class_outcomes() -> None:
    v = get_vocabulary()
    assert v.hypothesis_types["normal"].kind == "outcome"
    assert v.hypothesis_types["insufficient_evidence"].kind == "outcome"


def test_hypothesis_families_match_scenario_families() -> None:
    families = set(get_value(load_config("generation"), "scenario_families"))
    mapped = {h.family for h in get_vocabulary().hypothesis_types.values() if h.family}
    assert mapped <= families
    # every non-interop scenario family is covered by at least one hypothesis type
    assert families - mapped == {"interop_failure"}


# ----------------------------------------------------------------------------- round trips
@pytest.mark.parametrize("t", ALL_TYPES)
def test_every_message_type_round_trips(t: MessageType) -> None:
    msg = pf.message(t)
    assert type(msg) is MESSAGE_CLASSES[t]
    assert parse_message(to_json(msg)) == msg
    assert parse_message(dump_message(msg)) == msg


def test_msg_id_is_deterministic_and_content_addressed() -> None:
    a = pf.message(MessageType.CLUE)
    b = pf.message(MessageType.CLUE)
    assert a.msg_id == b.msg_id
    later = make_message(
        MessageType.CLUE,
        sender="agent-x",
        correlation_id=pf.INCIDENT,
        payload=pf.clue(),
        timestamp=pf.T0 + timedelta(hours=1),
    )
    assert later.msg_id == a.msg_id, "timestamp must not affect msg_id"
    other = make_message(
        MessageType.CLUE,
        sender="agent-x",
        correlation_id=pf.INCIDENT,
        payload=pf.clue("observation-1"),
        timestamp=pf.T0,
    )
    assert other.msg_id != a.msg_id
    assert a.msg_id.startswith("clue-")


def test_causation_chain_sets_depth() -> None:
    root = pf.message(MessageType.OBSERVATION)
    child = pf.message(MessageType.CLUE, parent=root)
    grandchild = pf.message(MessageType.HYPOTHESIS, parent=child)
    assert (root.depth, child.depth, grandchild.depth) == (0, 1, 2)
    assert grandchild.causation_id == child.msg_id


@settings(max_examples=60, deadline=None)
@given(
    values=st.lists(
        st.floats(min_value=0, max_value=100, allow_nan=False), min_size=1, max_size=20
    ),
    q=st.floats(min_value=0, max_value=1),
)
def test_observation_round_trip_property(values: list[float], q: float) -> None:
    quality = pf.Q.model_copy(update={"score": q})
    payload = ObservationPayload(
        entity=pf.LINK,
        metric="packet_loss",
        unit="percent",
        quality=quality,
        points=tuple(Point(t=pf.T0 + timedelta(minutes=i), v=v) for i, v in enumerate(values)),
    )
    msg = make_message(
        MessageType.OBSERVATION,
        sender="translator",
        correlation_id="p",
        payload=payload,
        timestamp=pf.T0,
    )
    assert parse_message(to_json(msg)) == msg


@settings(max_examples=40, deadline=None)
@given(text=st.text(max_size=40))
def test_parser_never_crashes_on_garbage(text: str) -> None:
    with pytest.raises(ValidationError):
        parse_message(json.dumps({"type": text, "payload": text}))


# ----------------------------------------------------------------------------- rejection
def _wire(t: MessageType) -> dict:  # type: ignore[type-arg]
    return copy.deepcopy(dump_message(pf.message(t)))


@pytest.mark.parametrize(
    ("t", "path", "value", "why"),
    [
        (MessageType.OBSERVATION, ("payload", "metric"), "latency_ms", "unknown metric"),
        (MessageType.OBSERVATION, ("payload", "unit"), "ratio", "non-canonical unit"),
        (MessageType.OBSERVATION, ("payload", "metric"), "cpu_utilization", "metric not for links"),
        (
            MessageType.OBSERVATION,
            ("payload", "entity", "entity_type"),
            "toaster",
            "unknown entity type",
        ),
        (MessageType.CLUE, ("payload", "unit"), "ms", "wrong clue unit"),
        (MessageType.CLUE, ("payload", "deviation"), -1, "negative deviation"),
        (MessageType.HYPOTHESIS, ("payload", "local_confidence"), 1.5, "confidence > 1"),
        (
            MessageType.HYPOTHESIS,
            ("payload", "hypothesis_type"),
            "insufficient_evidence",
            "not proposable",
        ),
        (
            MessageType.REQUEST,
            ("payload", "capability"),
            "metric:nonsense",
            "unknown capability metric",
        ),
        (MessageType.CLUE, ("protocol_version",), "9.9", "wrong version"),
        (MessageType.CLUE, ("schema_version",), "0.0", "wrong vocabulary"),
        (MessageType.CLUE, ("timestamp",), "2026-01-01T00:00:00", "naive timestamp"),
        (MessageType.ERROR, ("payload", "code"), "OOPS", "unknown error code"),
    ],
)
def test_invalid_messages_rejected(
    t: MessageType, path: tuple[str, ...], value: object, why: str
) -> None:
    w = _wire(t)
    node = w
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value
    with pytest.raises(ValidationError):
        parse_message(w)


def test_out_of_range_sample_rejected() -> None:
    w = _wire(MessageType.OBSERVATION)
    w["payload"]["points"][0]["v"] = 140.0  # utilization is a percentage
    with pytest.raises(ValidationError, match="physical range"):
        parse_message(w)


def test_unordered_points_rejected() -> None:
    w = _wire(MessageType.OBSERVATION)
    w["payload"]["points"].reverse()
    with pytest.raises(ValidationError, match="time order"):
        parse_message(w)


def test_unknown_envelope_field_rejected() -> None:
    w = _wire(MessageType.ACK)
    w["priority"] = "high"
    with pytest.raises(ValidationError):
        parse_message(w)


def test_payload_must_match_type() -> None:
    w = _wire(MessageType.CLUE)
    w["payload"] = _wire(MessageType.OBSERVATION)["payload"]
    with pytest.raises(ValidationError):
        parse_message(w)


def test_topology_edge_must_reference_nodes() -> None:
    w = _wire(MessageType.TOPOLOGY)
    w["payload"]["edges"][0]["b"] = "ghost"
    with pytest.raises(ValidationError, match="unknown nodes"):
        parse_message(w)


def test_enum_metric_values_checked() -> None:
    ok = ObservationPayload(
        entity=pf.SWITCH,
        metric="device_status",
        unit="state",
        quality=pf.Q,
        points=(Point(t=pf.T0, v="down"),),
    )
    assert ok.points[0].v == "down"
    with pytest.raises(ValidationError):
        ObservationPayload(
            entity=pf.SWITCH,
            metric="device_status",
            unit="state",
            quality=pf.Q,
            points=(Point(t=pf.T0, v="exploded"),),
        )


# ----------------------------------------------------------------------------- versions
@pytest.mark.parametrize("t", sorted(V1_TYPES))
def test_downgrade_then_upgrade_preserves_core_fields(t: str) -> None:
    original = pf.message(MessageType(t))
    v1 = convert(dump_message(original), V1)
    assert v1["version"] == V1 and "msg_id" not in v1
    assert any(a.startswith("lossy:") for a in v1["adaptations"])
    back = upgrade(v1)
    assert type(back) is type(original)
    assert (back.msg_id, back.correlation_id, back.sender, back.type) == (
        original.msg_id,
        original.correlation_id,
        original.sender,
        original.type,
    )
    assert f"{V1}->{V2}" in back.adaptations


def test_hand_written_v1_message_is_upgraded() -> None:
    v1 = {
        "protocol": "netcoop",
        "version": "1.0",
        "id": "ext-1",
        "incident": "inc-ext",
        "from": "external-probe",
        "time": "2026-01-01T00:00:00Z",
        "type": "HYPOTHESIS",
        "payload": {
            "hypothesis": "weak_wifi_signal",
            "entities": [{"id": "ap-1", "type": "access_point"}],
            "confidence_pct": 40,
        },
    }
    msg = upgrade(v1)
    assert isinstance(msg.payload, HypothesisPayload)
    assert msg.payload.local_confidence == pytest.approx(0.4)
    assert msg.recipient == "board"
    assert "assumed:entity_roles=root" in msg.adaptations


def test_v1_observation_gets_flagged_assumed_quality() -> None:
    w = convert(dump_message(pf.message(MessageType.OBSERVATION)), V1)
    msg = upgrade(w)
    assert isinstance(msg.payload, ObservationPayload)
    assert "quality_unknown_v1" in msg.payload.quality.issues
    assert msg.payload.quality.score == get_value(
        load_config("protocol"), "v1_upgrade.assumed_data_quality"
    )


@pytest.mark.parametrize("t", sorted(set(MessageType) - {MessageType(x) for x in V1_TYPES}))
def test_downgrade_of_v2_only_types_is_refused(t: MessageType) -> None:
    with pytest.raises(VersionError) as err:
        convert(dump_message(pf.message(t)), V1)
    assert err.value.code is ErrorCode.UNSUPPORTED_MESSAGE_TYPE


def test_malformed_v1_is_typed_error() -> None:
    with pytest.raises(VersionError) as err:
        upgrade({"protocol": "netcoop", "version": "1.0", "type": "ACK", "payload": {}})
    assert err.value.code is ErrorCode.MALFORMED_INPUT


@pytest.mark.parametrize(
    ("data", "code"),
    [
        ({"protocol": "netcoop", "version": "7.0", "type": "ACK"}, ErrorCode.INCOMPATIBLE_VERSION),
        ({"protocol": "other", "version": "1.0"}, ErrorCode.INCOMPATIBLE_SCHEMA),
        ({"protocol": "netcoop"}, ErrorCode.MISSING_FIELD),
    ],
)
def test_unconvertible_inputs(data: dict, code: ErrorCode) -> None:  # type: ignore[type-arg]
    with pytest.raises(VersionError) as err:
        upgrade(data)
    assert err.value.code is code


def test_negotiation() -> None:
    assert supported_versions() == (V1, V2)
    assert negotiate([V1, V2], [V2]) == V2
    assert negotiate([V1, V2], [V1]) == V1
    with pytest.raises(VersionError):
        negotiate([V2], ["3.0"])


# ----------------------------------------------------------------------------- capability
def test_capability_routing() -> None:
    card = pf.card_for("perf", activation_metrics=("utilization",))
    assert card.wants(MessageType.OBSERVATION, "utilization")
    assert not card.wants(MessageType.OBSERVATION, "rssi")
    assert not card.wants(MessageType.CLUE)
    assert card.can_serve("metric:egress_queue_drops")
    assert not card.can_serve("metric:rssi")
    assert not card.can_serve("analysis:upstream_path")
    assert card.is_active({"utilization", "rssi"})
    assert not card.is_active({"rssi"})


def test_capability_card_validates_vocabulary() -> None:
    with pytest.raises(ValidationError):
        pf.card_for("bad", consumes_metrics=("bogus",))
    with pytest.raises(ValidationError):
        pf.card_for(
            "bad", produces_types=(MessageType.CLUE,)
        )  # lists hypotheses but can't produce them


# ----------------------------------------------------------------------------- report & docs
def test_report_top_level_keys_are_exactly_a7_plus_namespace() -> None:
    a7 = {
        "incident_id",
        "status",
        "suspected_root_cause",
        "confidence",
        "affected_devices",
        "supporting_evidence",
        "alternative_causes",
        "recommended_actions",
        "evidence_sources",
        "limitations",
    }
    assert set(Report.model_fields) == a7 | {"x_netcoop"}
    assert set(Report.model_fields["supporting_evidence"].annotation.__args__[0].model_fields) == {
        "metric",
        "value",
        "interpretation",
    }


def _all_models() -> set[type[BaseModel]]:
    seen: set[type[BaseModel]] = set()
    stack: list[type[BaseModel]] = list(MESSAGE_CLASSES.values())
    while stack:
        m = stack.pop()
        if m in seen:
            continue
        seen.add(m)
        for f in m.model_fields.values():
            stack += schema_export._nested_models(f.annotation)
    return seen


def test_every_field_is_documented() -> None:
    missing = [
        f"{m.__name__}.{n}"
        for m in _all_models()
        for n, f in m.model_fields.items()
        if not f.description
    ]
    assert not missing


def test_exported_schemas_are_current() -> None:
    for name, schema in schema_export.build_schemas().items():
        on_disk = json.loads((schema_export.SCHEMA_DIR / name).read_text(encoding="utf-8"))
        assert on_disk == schema, f"{name} is stale: run `netcoop schemas`"
    assert schema_export.REFERENCE.read_text(encoding="utf-8") == schema_export.build_reference()


def test_protocol_doc_examples_are_valid() -> None:
    import re

    doc = (schema_export.DOCS / "PROTOCOL.md").read_text(encoding="utf-8")
    blocks = re.findall(r"<!-- example:(v\d) -->\s*```json\n(.*?)```", doc, flags=re.S)
    assert {v for v, _ in blocks} == {"v1", "v2"}
    for version, body in blocks:
        data = json.loads(body)
        msg = parse_message(data) if version == "v2" else upgrade(data)
        assert msg.correlation_id


def test_content_id_uses_configured_length() -> None:
    n = get_value(load_config("protocol"), "msg_id_hash_hex_chars")
    mid = content_id(MessageType.ACK, "a", "b", None, pf.payloads()[MessageType.ACK])
    assert len(mid.split("-", 1)[1]) == n


def test_timestamps_are_timezone_aware() -> None:
    msg = pf.message(MessageType.ACK)
    assert isinstance(msg.timestamp, datetime) and msg.timestamp.utcoffset() is not None
