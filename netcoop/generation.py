"""Labelled dataset generation around the organiser's telemetry generator.

The organiser's Colab generator is integrated through a thin adapter module at
``generator/adapter.py`` exposing::

    def generate(scenario: str, seed: int, intensity: float, noise: float,
                 missing_rate: float, out_dir: pathlib.Path) -> list[pathlib.Path]

``scenario`` is one of our canonical scenario labels (config/generation.yaml);
the adapter translates it to the generator's native identifiers. The adapter
writes raw generator output into ``out_dir`` and returns the written files.
This module owns the sweep, the directory layout and the ground-truth metadata.
"""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from netcoop.config import get_value, load_config

REPO_ROOT = Path(__file__).resolve().parent.parent
ADAPTER_PATH = REPO_ROOT / "generator" / "adapter.py"
DEFAULT_OUT = REPO_ROOT / "data" / "generated"
META_FILE = "meta.json"
GROUND_TRUTH_FILE = "ground_truth.json"
LABEL_FILES = frozenset({META_FILE, GROUND_TRUTH_FILE})

GenerateFn = Callable[..., list[Path]]


class GeneratorUnavailable(Exception):
    """The organiser's generator has not been integrated yet."""


def load_adapter(path: Path = ADAPTER_PATH) -> ModuleType:
    if not path.is_file():
        raise GeneratorUnavailable(
            f"Organiser generator adapter not found at {path}. Place the organiser's "
            "Colab generator code under generator/ and add generator/adapter.py "
            "(see netcoop/generation.py for the required interface)."
        )
    spec = importlib.util.spec_from_file_location("netcoop_generator_adapter", path)
    if spec is None or spec.loader is None:
        raise GeneratorUnavailable(f"cannot import adapter at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if not callable(getattr(module, "generate", None)):
        raise GeneratorUnavailable(f"{path} does not define generate(...)")
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_sweep(
    out_dir: Path = DEFAULT_OUT,
    scenarios: list[str] | None = None,
    seeds: list[int] | None = None,
    generate_fn: GenerateFn | None = None,
) -> list[Path]:
    """Generate every sweep cell; returns the list of run directories.

    Each run directory contains the raw generator files plus ``meta.json`` with
    the exact generator parameters, which is the ground-truth label.
    """
    cfg = load_config("generation")
    families: list[str] = get_value(cfg, "scenario_families")
    scenarios = scenarios or families
    unknown = sorted(set(scenarios) - set(families))
    if unknown:
        raise ValueError(f"unknown scenario families {unknown}; known: {families}")
    seeds = seeds if seeds is not None else get_value(cfg, "sweep.seeds")
    intensities: list[float] = get_value(cfg, "sweep.intensities")
    noises: list[float] = get_value(cfg, "sweep.noise_levels")
    missings: list[float] = get_value(cfg, "sweep.missing_rates")

    if generate_fn is None:
        generate_fn = load_adapter().generate

    run_dirs: list[Path] = []
    for scenario, seed, intensity, noise, missing in itertools.product(
        scenarios, seeds, intensities, noises, missings
    ):
        run_id = f"{scenario}__s{seed}__i{intensity}__n{noise}__m{missing}"
        run_dir = out_dir / scenario / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        params: dict[str, Any] = {
            "scenario": scenario,
            "seed": seed,
            "intensity": intensity,
            "noise": noise,
            "missing_rate": missing,
        }
        files = generate_fn(out_dir=run_dir, **params)
        truth = dict(params)
        gt_file = run_dir / GROUND_TRUTH_FILE
        if gt_file.is_file():
            # Generator-reported labels (root cause, target entity, affected entities)
            # extend the sweep parameters; sweep parameters win on conflict.
            truth = {**json.loads(gt_file.read_text(encoding="utf-8")), **params}
        meta = {
            "run_id": run_id,
            "ground_truth": truth,
            "files": {p.name: _sha256(p) for p in sorted(files)},
        }
        (run_dir / META_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8", newline="\n")
        run_dirs.append(run_dir)
    return run_dirs
