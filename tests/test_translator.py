"""Phase 2 tests: Translator layers, canonical correctness and the mutated corpus."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from netcoop.generation import load_adapter
from netcoop.mutation import MUTATORS, run_corpus
from netcoop.protocol.common import ErrorCode, MessageType, Severity
from netcoop.protocol.messages import parse_message, to_json
from netcoop.translator.issues import IssueLog
from netcoop.translator.quality import combine
from netcoop.translator.readers import parse_timestamp, read_path
from netcoop.translator.translator import Translator

# (scenario, seed, intensity, noise, missing): one native clean, one native degraded, two legacy.
RUN_PARAMS = [
    ("link_congestion", 11, 1.0, 0.0, 0.0),
    ("weak_wifi", 12, 0.5, 0.25, 0.3),
    ("interop_failure", 13, 0.75, 0.1, 0.0),
    ("interop_failure", 14, 0.25, 0.25, 0.3),
]


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    adapter = load_adapter()
    out = []
    for scenario, seed, intensity, noise, missing in RUN_PARAMS:
        d = tmp_path_factory.mktemp(f"{scenario}_{seed}")
        adapter.generate(
            scenario=scenario,
            seed=seed,
            intensity=intensity,
            noise=noise,
            missing_rate=missing,
            out_dir=d,
        )
        out.append(d)
    return out


@pytest.fixture(scope="module")
def tr() -> Translator:
    return Translator()


# ----------------------------------------------------------------------------- correctness
def test_native_values_match_raw_records(runs: list[Path], tr: Translator) -> None:
    run = runs[0]
    res = tr.translate(run, "t")
    raw = [json.loads(line) for line in (run / "telemetry.jsonl").read_text().splitlines()]
    link = next(r for r in raw if r["kind"] == "link" and "latency_ms" in r)
    obs = res.series(link["link_id"], "latency")
    assert obs is not None
    t = datetime.fromisoformat(link["ts"].replace("Z", "+00:00"))
    assert next(p.v for p in obs.points if p.t == t) == pytest.approx(link["latency_ms"])
    ap = next(r for r in raw if r["kind"] == "wireless" and "loss_pct" in r)
    assert res.series(ap["ap_id"], "wireless_packet_loss") is not None, (
        "wireless loss must not become link loss"
    )


def test_legacy_units_are_converted(runs: list[Path], tr: Translator) -> None:
    run = runs[2]
    res = tr.translate(run, "t")
    with (run / "link_stats.csv").open() as fh:
        row = next(r for r in csv.DictReader(fh) if r["latency_us"] and r["util_ratio"])
    link = f"{row['src']}--{row['dst']}"
    t = datetime.fromtimestamp(int(row["time"]), tz=UTC)
    lat = res.series(link, "latency")
    util = res.series(link, "utilization")
    assert lat is not None and util is not None
    assert next(p.v for p in lat.points if p.t == t) == pytest.approx(
        float(row["latency_us"]) / 1000
    )
    assert next(p.v for p in util.points if p.t == t) == pytest.approx(
        float(row["util_ratio"]) * 100
    )
    assert set(res.dialects.values()) == {"legacy_v1"}


def test_both_dialects_yield_same_metric_vocabulary(runs: list[Path], tr: Translator) -> None:
    native = {o.metric for o in tr.translate(runs[0], "a").observations}
    legacy = {o.metric for o in tr.translate(runs[2], "b").observations}
    assert native == legacy


def test_topology_and_root_recovered_in_both_dialects(runs: list[Path], tr: Translator) -> None:
    for run in (runs[0], runs[2]):
        topo = tr.translate(run, "t").topology
        assert topo is not None and topo.upstream_root is not None
        assert all(e.directed for e in topo.edges)


def test_label_files_are_never_read(runs: list[Path], tr: Translator) -> None:
    res = tr.translate(runs[0], "t")
    sources = {s.source for o in res.observations for s in o.sources}
    assert not sources & {"ground_truth.json", "meta.json"}


def test_messages_are_valid_protocol_and_deterministic(runs: list[Path], tr: Translator) -> None:
    a = tr.translate(runs[1], "inc-x")
    b = tr.translate(runs[1], "inc-x")
    assert [m.msg_id for m in a.messages] == [m.msg_id for m in b.messages]
    assert a.messages[0].type is MessageType.TOPOLOGY
    for m in a.messages[:20]:
        assert parse_message(to_json(m)) == m


def test_missing_data_lowers_quality(runs: list[Path], tr: Translator) -> None:
    clean = tr.translate(runs[0], "a").entity_quality
    sparse = tr.translate(runs[1], "b").entity_quality
    assert sum(sparse.values()) / len(sparse) < sum(clean.values()) / len(clean)


# --- mutated corpus (Phase 2 exit criterion) ---
def test_mutated_corpus_no_failures_no_crashes(
    runs: list[Path], tr: Translator, tmp_path: Path
) -> None:
    rows = run_corpus(runs, tmp_path, tr)
    bad = [
        (r.kind, r.run, r.detail, r.failures[:2]) for r in rows if r.outcome in ("fail", "crash")
    ]
    assert not bad
    applicable = {r.kind for r in rows if r.outcome == "pass"}
    assert applicable == set(MUTATORS), f"never exercised: {set(MUTATORS) - applicable}"


# ----------------------------------------------------------------------------- unit level
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-10-01T09:00:00Z", datetime(2026, 10, 1, 9, tzinfo=UTC)),
        ("2026-10-01T11:00:00+02:00", datetime(2026, 10, 1, 9, tzinfo=UTC)),
        ("2026-10-01T09:00:00", datetime(2026, 10, 1, 9, tzinfo=UTC)),
        (1790845200, datetime.fromtimestamp(1790845200, tz=UTC)),
        ("1790845200", datetime.fromtimestamp(1790845200, tz=UTC)),
        (1790845200000, datetime.fromtimestamp(1790845200, tz=UTC)),
        ("yesterday", None),
        (True, None),
        (float("nan"), None),
    ],
)
def test_parse_timestamp(raw: object, expected: datetime | None) -> None:
    assert parse_timestamp(raw, 1e11) == expected


def _write(d: Path, name: str, text: str) -> Path:
    p = d / name
    p.write_text(text, encoding="utf-8")
    return p


def test_readers_report_instead_of_raising(tmp_path: Path) -> None:
    log = IssueLog()
    assert read_path(_write(tmp_path, "empty.csv", ""), log) == []
    assert read_path(_write(tmp_path, "bad.json", "{oops"), log) == []
    tables = read_path(
        _write(tmp_path, "mixed.jsonl", '{"a": 1}\nnot json\n[1,2]\n{"a": 2}\n'), log
    )
    assert len(tables[0].records) == 2
    sniffed = read_path(_write(tmp_path, "noext", '{"a": 1}\n{"a": 2}\n'), log)
    assert sniffed[0].fmt == "jsonl"
    assert {i.code for i in log} == {ErrorCode.MALFORMED_INPUT}
    assert any(i.severity is Severity.FATAL for i in log)


def test_unknown_field_preserved_with_suggestion(tmp_path: Path, tr: Translator) -> None:
    _write(
        tmp_path,
        "t.csv",
        "time,hostname,cpu_pctt,mystery\n1790845200,sw1,12,abc\n1790845260,sw1,13,def\n",
    )
    res = tr.translate(tmp_path, "t")
    unknown = [e for e in res.errors if e.code is ErrorCode.UNKNOWN_FIELD]
    assert {e.source.raw_field for e in unknown if e.source} == {"cpu_pctt", "mystery"}
    assert any(e.context.get("suggestion") == "cpu_pct" for e in unknown)
    assert res.unknown_fields["t.csv"]["mystery"] == ["abc", "def"]
    assert not res.observations, "suggestions must never be applied"


@pytest.mark.parametrize(("values", "factor"), [(["0.2", "0.4"], 100.0), (["20", "40"], 1.0)])
def test_ambiguous_proportion_unit_inferred_and_flagged(
    tmp_path: Path, tr: Translator, values: list[str], factor: float
) -> None:
    rows = "".join(f"{1790845200 + 60 * i},sw1,{v}\n" for i, v in enumerate(values))
    _write(tmp_path, "t.csv", "time,hostname,cpu\n" + rows)
    res = tr.translate(tmp_path, "t")
    obs = res.series("sw1", "cpu_utilization")
    assert obs is not None
    assert [p.v for p in obs.points] == pytest.approx([float(v) * factor for v in values])
    assert "AMBIGUOUS_UNIT" in obs.quality.issues
    assert obs.quality.mapping_certainty < 1


def test_no_topology_degrades_gracefully(tmp_path: Path, tr: Translator) -> None:
    _write(tmp_path, "t.csv", "time,hostname,state\n1790845200,sw1,UP\n1790845260,sw1,down\n")
    res = tr.translate(tmp_path, "t")
    assert ErrorCode.MISSING_TOPOLOGY in res.error_codes()
    obs = res.series("sw1", "device_status")
    assert obs is not None and [p.v for p in obs.points] == ["up", "down"]
    assert obs.entity.entity_type == "device"


def test_topology_from_parent_pointers_only(tmp_path: Path, tr: Translator) -> None:
    topo = {
        "devices": [{"name": "r1", "kind": "rtr"}, {"name": "s1", "kind": "sw", "upstream": "r1"}]
    }
    _write(tmp_path, "topo.json", json.dumps(topo))
    _write(tmp_path, "t.csv", "time,src,dst,loss_ratio\n1790845200,r1,s1,0.01\n")
    res = tr.translate(tmp_path, "t")
    assert res.topology is not None and res.topology.upstream_root == "r1"
    (edge,) = res.topology.edges
    assert (edge.a, edge.b, edge.directed) == ("r1", "s1", True)
    obs = res.series(edge.link_id, "packet_loss")
    assert obs is not None and obs.points[0].v == pytest.approx(1.0)


def test_metric_not_applicable_to_entity_is_reported(tmp_path: Path, tr: Translator) -> None:
    _write(tmp_path, "t.csv", "time,link_id,rssi_dbm\n1790845200,a--b,-60\n")
    res = tr.translate(tmp_path, "t")
    assert ErrorCode.INAPPLICABLE_METRIC in res.error_codes()
    assert not res.observations


def test_nothing_to_read_is_a_typed_error(tmp_path: Path, tr: Translator) -> None:
    res = tr.translate(tmp_path, "t")
    assert ErrorCode.MALFORMED_INPUT in res.error_codes()
    assert res.observations == [] and res.topology is None


def test_quality_is_geometric_mean() -> None:
    q = combine(1.0, 1.0, 0.25, 1.0)
    assert q.score == pytest.approx(0.25**0.25)
    assert combine(0.0, 1.0, 1.0, 1.0).score == 0.0
