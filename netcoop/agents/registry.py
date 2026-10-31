"""Agent registry: plugins register themselves; the orchestrator never names agents.

Any module inside the ``netcoop.agents`` package (and any module passed to ``discover``)
can register agent classes with ``@register_agent``. Adding an agent therefore means
adding a module: no engine change.
"""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
import sys
from collections.abc import Callable

from netcoop.agents.base import Agent
from netcoop.extensions import plugin_files, plugin_modules

AgentFactory = Callable[[], Agent]
_REGISTRY: dict[str, type[Agent]] = {}
_DISCOVERED = False


def register_agent(cls: type[Agent]) -> type[Agent]:
    agent_id = cls.card.agent_id
    if agent_id in _REGISTRY and _REGISTRY[agent_id] is not cls:
        raise ValueError(f"duplicate agent_id {agent_id!r}")
    _REGISTRY[agent_id] = cls
    return cls


def discover(extra_modules: tuple[str, ...] = ()) -> None:
    """Import every module under netcoop.agents (plus extras) so they can register."""
    global _DISCOVERED
    import netcoop.agents as pkg

    if not _DISCOVERED:
        for mod in pkgutil.iter_modules(pkg.__path__, prefix=f"{pkg.__name__}."):
            if mod.name.rsplit(".", 1)[-1] not in ("base", "registry"):
                importlib.import_module(mod.name)
        for name in plugin_modules():
            importlib.import_module(name)
        for path in plugin_files():
            spec = importlib.util.spec_from_file_location(f"netcoop_plugin_{path.stem}", path)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load plugin {path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        _DISCOVERED = True
    for name in extra_modules:
        importlib.import_module(name)


def registered() -> dict[str, type[Agent]]:
    discover()
    return dict(sorted(_REGISTRY.items()))


def create_agents() -> list[Agent]:
    """Fresh instances of every registered agent, in agent_id order."""
    return [cls() for _, cls in registered().items()]
