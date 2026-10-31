"""Phase 0 tests: config justification, sweep metadata, profiler, CLI errors."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from netcoop.cli.main import main
from netcoop.config import CONFIG_DIR, ConfigError, config_hash, get_value, load_config
from netcoop.generation import GeneratorUnavailable, load_adapter, run_sweep
from netcoop.profiling import profile_directory, render_markdown


def test_all_shipped_configs_are_justified() -> None:
    for path in CONFIG_DIR.glob("*.yaml"):
        load_config(path.stem)


def test_bare_value_rejected(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text("threshold: 42\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="bare value"):
        load_config("bad", tmp_path)


def test_entry_missing_source_rejected(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text(
        "t:\n  value: 1\n  unit: ms\n  rationale: because\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="source"):
        load_config("bad", tmp_path)


def test_config_hash_is_stable() -> None:
    assert config_hash() == config_hash()


def _fake_generate(out_dir: Path, **params: object) -> list[Path]:
    # Test double only: proves the sweep records ground truth and hashes outputs.
    p = out_dir / "telemetry.jsonl"
    p.write_text(json.dumps({"x": params["seed"]}) + "\n", encoding="utf-8")
    return [p]


def test_sweep_writes_ground_truth(tmp_path: Path) -> None:
    cfg = load_config("generation")
    families = get_value(cfg, "scenario_families")
    runs = run_sweep(tmp_path, scenarios=families[:2], seeds=[0], generate_fn=_fake_generate)
    n_cells = (
        len(get_value(cfg, "sweep.intensities"))
        * len(get_value(cfg, "sweep.noise_levels"))
        * len(get_value(cfg, "sweep.missing_rates"))
    )
    assert len(runs) == 2 * n_cells
    meta = json.loads((runs[0] / "meta.json").read_text(encoding="utf-8"))
    assert meta["ground_truth"]["scenario"] == families[0]
    assert "telemetry.jsonl" in meta["files"]


def test_sweep_rejects_unknown_scenario(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown scenario"):
        run_sweep(tmp_path, scenarios=["not_a_family"], generate_fn=_fake_generate)


def test_missing_adapter_is_reported(tmp_path: Path) -> None:
    with pytest.raises(GeneratorUnavailable):
        load_adapter(tmp_path / "adapter.py")


def test_profiler_is_schema_agnostic(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("col_a,col_b\n1,x\n2,\n", encoding="utf-8")
    (tmp_path / "b.jsonl").write_text('{"k": {"n": 3}}\n{"k": {"n": 4}}\n', encoding="utf-8")
    prof = profile_directory(tmp_path, max_examples=3)
    assert {f["field"] for f in prof["a.csv"]} == {"col_a", "col_b"}
    assert {f["field"] for f in prof["b.jsonl"]} == {"k.n"}
    assert "`col_a`" in render_markdown(prof, tmp_path)


def test_cli_profile_empty_dir_errors(tmp_path: Path) -> None:
    assert main(["profile", "--input", str(tmp_path), "--out", str(tmp_path / "p.md")]) == 2
