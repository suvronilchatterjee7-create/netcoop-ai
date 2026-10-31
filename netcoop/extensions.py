"""Extension points: add faults and agents without touching the engine (docs/EXTENDING.md).

* ``NETCOOP_EXTENSIONS`` - one or more directories (separated by the OS path separator), each
  optionally containing:

      vocabulary/hypothesis_types.yaml   new fault types         (merged into data/vocabulary)
      catalogue/hypotheses.yaml          their signatures         (merged into config/catalogue)
      catalogue/agents.yaml              new data-defined agents  (merged into config/catalogue)
      plugins/*.py                       code agents that self-register with @register_agent

* ``NETCOOP_PLUGINS`` - comma-separated importable module names with agent plugins.

Entries in an extension may add new keys but never redefine existing ones (an extension
cannot silently change the shipped behaviour).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def extension_dirs() -> list[Path]:
    raw = os.environ.get("NETCOOP_EXTENSIONS", "")
    return [Path(p) for p in raw.split(os.pathsep) if p.strip()]


def plugin_modules() -> list[str]:
    return [m.strip() for m in os.environ.get("NETCOOP_PLUGINS", "").split(",") if m.strip()]


def plugin_files() -> list[Path]:
    return [f for d in extension_dirs() for f in sorted((d / "plugins").glob("*.py"))]


def merge_section(base: dict[str, Any], relpath: str, section: str) -> dict[str, Any]:
    """Merge ``section`` of every extension's ``relpath`` YAML into ``base`` (new keys only)."""
    out = dict(base)
    for d in extension_dirs():
        f = d / relpath
        if not f.is_file():
            continue
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        for key, value in (data.get(section) or {}).items():
            if key in out:
                raise ValueError(f"extension {f} redefines existing {section} entry {key!r}")
            out[key] = value
    return out
