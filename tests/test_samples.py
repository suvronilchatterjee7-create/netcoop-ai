"""Committed samples (data/samples) and the scripted demo (Phase 10)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from netcoop.demo import SAMPLES, run_demo
from netcoop.generation import load_adapter

SAMPLE_DIRS = sorted(d for d in SAMPLES.iterdir() if d.is_dir())


def test_samples_present() -> None:
    assert len(SAMPLE_DIRS) >= 9
    for d in SAMPLE_DIRS:
        gt = json.loads((d / "meta.json").read_text(encoding="utf-8"))["ground_truth"]
        assert gt["seed"] >= 100, f"{d.name}: samples must not come from training/dev seeds"


@pytest.mark.parametrize("sample", SAMPLE_DIRS, ids=lambda d: d.name)
def test_sample_regenerates_identically(sample: Path, tmp_path: Path) -> None:
    gt = json.loads((sample / "meta.json").read_text(encoding="utf-8"))["ground_truth"]
    load_adapter().generate(
        scenario=sample.name.split("__")[0],
        seed=gt["seed"],
        intensity=gt["intensity"],
        noise=gt["noise"],
        missing_rate=gt["missing_rate"],
        out_dir=tmp_path,
    )
    for f in sorted(tmp_path.iterdir()):
        assert f.read_bytes() == (sample / f.name).read_bytes(), f"{sample.name}/{f.name}"


def test_demo_scenes_meet_expectations() -> None:
    lines: list[str] = []
    assert run_demo(out_dir=None, write=lines.append) == 0
    text = "\n".join(lines)
    assert "decision chain" in text and "outcome: resolved" in text
    assert "outcome: deferred" in text and "precision of claims" in text
