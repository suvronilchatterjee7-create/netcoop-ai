"""Generator adapter used by ``netcoop generate``.

Currently backed by the provisional stand-in generator (``generator/synth.py``,
decision D-004). To switch to the organiser's Colab generator, reimplement
``generate`` here so it calls their code and maps our canonical scenario labels
to their native identifiers; nothing else in the repository needs to change.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "netcoop_synth", Path(__file__).with_name("synth.py")
)
assert _spec is not None and _spec.loader is not None
_synth = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _synth  # dataclasses resolve annotations via sys.modules
_spec.loader.exec_module(_synth)


def generate(
    scenario: str, seed: int, intensity: float, noise: float, missing_rate: float, out_dir: Path
) -> list[Path]:
    files: list[Path] = _synth.generate(scenario, seed, intensity, noise, missing_rate, out_dir)
    return files
