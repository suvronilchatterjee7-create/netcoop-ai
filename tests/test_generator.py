"""Tests for the stand-in generator through the public adapter interface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from netcoop.config import get_value, load_config
from netcoop.generation import load_adapter, run_sweep

FAMILIES: list[str] = get_value(load_config("generation"), "scenario_families")


@pytest.fixture(scope="module")
def adapter():  # type: ignore[no-untyped-def]
    return load_adapter()


def _run(adapter, tmp: Path, scenario: str, **kw: float) -> dict:  # type: ignore[no-untyped-def,type-arg]
    params = {"seed": 7, "intensity": 1.0, "noise": 0.0, "missing_rate": 0.0, **kw}
    files = adapter.generate(scenario=scenario, out_dir=tmp, **params)
    assert all(p.is_file() for p in files)
    return json.loads((tmp / "ground_truth.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("scenario", FAMILIES)
def test_every_family_generates_labelled_output(adapter, tmp_path: Path, scenario: str) -> None:  # type: ignore[no-untyped-def]
    gt = _run(adapter, tmp_path, scenario)
    assert gt["scenario"] == scenario
    if scenario == "normal":
        assert gt["target_entity"] is None and gt["affected_entities"] == []
    elif gt["root_cause"] != "normal":
        assert gt["target_entity"] in gt["affected_entities"]


def test_interop_family_uses_foreign_dialect(adapter, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    gt = _run(adapter, tmp_path, "interop_failure")
    (tmp_path / "n").mkdir()
    native = _run(adapter, tmp_path / "n", "normal")
    assert gt["dialect"] != native["dialect"]
    assert not (tmp_path / "telemetry.jsonl").exists()


def test_generation_is_deterministic(tmp_path: Path) -> None:
    a = run_sweep(tmp_path / "a", scenarios=FAMILIES[:2], seeds=[1])
    b = run_sweep(tmp_path / "b", scenarios=FAMILIES[:2], seeds=[1])
    for x, y in zip(a, b, strict=True):
        assert (x / "meta.json").read_text() == (y / "meta.json").read_text()


def test_missing_rate_drops_records(adapter, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    full, sparse = tmp_path / "full", tmp_path / "sparse"
    full.mkdir()
    sparse.mkdir()
    _run(adapter, full, "normal")
    _run(adapter, sparse, "normal", missing_rate=0.3)
    n_full = len((full / "telemetry.jsonl").read_text().splitlines())
    n_sparse = len((sparse / "telemetry.jsonl").read_text().splitlines())
    assert n_sparse < n_full


def test_sweep_meta_includes_generator_labels(tmp_path: Path) -> None:
    run = run_sweep(tmp_path, scenarios=[FAMILIES[1]], seeds=[0])[0]
    truth = json.loads((run / "meta.json").read_text())["ground_truth"]
    assert {"root_cause", "target_entity", "affected_entities", "seed"} <= set(truth)
