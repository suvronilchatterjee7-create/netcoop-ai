"""Local dashboard server (netcoop serve, docs/WEB.md)."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from netcoop.web import server as web

SAMPLE = "data/samples/link_congestion__s500__i1.0__n0.0__m0.0"


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    runs = tmp_path_factory.mktemp("web-runs")
    original = web._runs_dir
    web._runs_dir = lambda: runs  # type: ignore[assignment]
    srv = web.make_server(port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()
    web._runs_dir = original  # type: ignore[assignment]


def _get(base: str, path: str) -> bytes:
    with urllib.request.urlopen(base + path, timeout=120) as r:
        return bytes(r.read())


def _status(base: str, path: str) -> int:
    try:
        with urllib.request.urlopen(base + path, timeout=30) as r:
            return int(r.status)
    except urllib.error.HTTPError as exc:
        return exc.code


def test_binds_to_loopback() -> None:
    srv = web.make_server(port=0)
    try:
        assert srv.server_address[0] == "127.0.0.1"
    finally:
        srv.server_close()


def test_page_and_static(base: str) -> None:
    assert b"NetCoop AI" in _get(base, "/")
    assert b"renderFigure" in _get(base, "/static/app.js")
    assert _status(base, "/static/../server.py") == 404


def test_inputs_and_evaluation(base: str) -> None:
    inputs = json.loads(_get(base, "/api/inputs"))
    samples = next(c for c in inputs if c["collection"] == "data/samples")
    assert len(samples["runs"]) >= 9
    assert any(r["id"] == SAMPLE and r["truth"] == "link_congestion" for r in samples["runs"])
    rows = json.loads(_get(base, "/api/evaluation"))
    assert any("precision of claims" in k for k, _ in rows)


@pytest.mark.parametrize(
    "bad", ["../../netcoop", "data/samples/../../netcoop", "/etc/passwd", "data/samples/nope"]
)
def test_inputs_outside_roots_are_refused(base: str, bad: str) -> None:
    assert web.resolve_input(bad) is None
    assert _status(base, f"/api/diagnose?input={bad}") == 404


def test_live_diagnosis_stream_and_run_detail(base: str) -> None:
    body = _get(base, f"/api/diagnose?input={SAMPLE}").decode()
    events = [ln.split(": ", 1)[1] for ln in body.splitlines() if ln.startswith("event: ")]
    assert events[0] == "start" and events[-1] == "done"
    assert events.count("message") > 800
    incident = json.loads(body.strip().splitlines()[-1][len("data: ") :])["incident"]

    detail = json.loads(_get(base, f"/api/runs/{incident}"))
    assert detail["report"]["status"] == "diagnosed"
    types = [m["type"] for m in detail["chain"]]
    assert "HYPOTHESIS" in types and "VERDICT" in types and "OBSERVATION" not in types
    for prov in detail["report"]["x_netcoop"]["evidence_provenance"]:
        assert prov["clue_id"] in detail["cited"]
    assert detail["counts"]["OBSERVATION"]["translator"] > 0

    runs = json.loads(_get(base, "/api/runs"))
    assert runs[0]["incident"] == incident
    assert runs[0]["input"] == Path(SAMPLE).name
    assert _status(base, "/api/runs/..%2F..") == 404
