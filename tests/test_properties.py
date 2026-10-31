"""Property-based tests (Hypothesis): the Translator never raises, always emits valid messages."""

from __future__ import annotations

import csv
import io
import json
import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from netcoop.protocol.messages import parse_message, to_json
from netcoop.translator.mapping import get_mapping
from netcoop.translator.translator import Translator

MAPPING = get_mapping()
KNOWN = MAPPING.all_known_keys()
TRANSLATOR = Translator()

field_names = st.one_of(st.sampled_from(KNOWN), st.text(min_size=1, max_size=12))
values = st.one_of(
    st.floats(allow_nan=True, allow_infinity=True, width=32),
    st.integers(min_value=-(10**12), max_value=10**13),
    st.text(max_size=12),
    st.sampled_from(["UP", "down", "1790845200", "2026-10-01T09:00:00Z", "", "N/A", "sw1", "a--b"]),
)
records = st.lists(st.dictionaries(field_names, values, max_size=8), max_size=25)


def _csv(rows: list[dict[str, object]]) -> str:
    cols = list(dict.fromkeys(k for r in rows for k in r)) or ["x"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(rows=records, as_csv=st.booleans())
def test_translator_never_raises_on_arbitrary_tables(
    rows: list[dict[str, object]], as_csv: bool
) -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / ("t.csv" if as_csv else "t.jsonl")
        text = _csv(rows) if as_csv else "".join(json.dumps(r, default=str) + "\n" for r in rows)
        p.write_text(text, encoding="utf-8")
        res = TRANSLATOR.translate(p, "prop")
    for m in res.messages:
        assert parse_message(to_json(m)) == m
    for o in res.observations:
        assert 0 <= o.quality.score <= 1


@settings(max_examples=40, deadline=None)
@given(blob=st.binary(max_size=400), ext=st.sampled_from([".csv", ".json", ".jsonl", ".dat"]))
def test_translator_never_raises_on_arbitrary_bytes(blob: bytes, ext: str) -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / f"x{ext}"
        p.write_bytes(blob)
        res = TRANSLATOR.translate(p, "prop")
    assert all(parse_message(to_json(m)) == m for m in res.messages)
