"""Evaluation harness: run pipeline configurations over generated suites in parallel.

A *configuration* is a plain dict (picklable for worker processes):
    {"name": str, "agents": list[str] | None, "courtroom": bool, "corroboration": bool}
``agents=None`` means every registered agent. A worker returns one flat record per run with
the ground truth (from the generator's labels), the final decision and the correlator's
candidate ranking, so all metrics can be computed afterwards (metrics.py).
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import random
import shutil
import tempfile
from pathlib import Path
from typing import Any

from netcoop.correlation.fit import truth_locations
from netcoop.generation import META_FILE

Config = dict[str, Any]

FULL: Config = {"name": "full system", "agents": None, "courtroom": True, "corroboration": True}


def ablations(specialists: list[str]) -> list[Config]:
    """Configurations that test the architecture's claims (A11)."""
    out = [
        FULL,
        {"name": "without courtroom", "agents": None, "courtroom": False, "corroboration": True},
        {
            "name": "without corroboration (each hypothesis judged on its proposer's clues only)",
            "agents": None,
            "courtroom": True,
            "corroboration": False,
        },
        {
            "name": "without connectivity agent",
            "agents": [s for s in specialists if s != "connectivity"],
            "courtroom": True,
            "corroboration": True,
        },
    ]
    for s in specialists:
        if s != "connectivity":
            out.append(
                {
                    "name": f"single agent: {s}",
                    "agents": [s],
                    "courtroom": True,
                    "corroboration": True,
                }
            )
    return out


def _orchestrator(cfg: Config) -> Any:
    from netcoop.agents.registry import create_agents
    from netcoop.correlation.correlator import Correlator
    from netcoop.orchestrator.orchestrator import Orchestrator

    agents = create_agents()
    if cfg["agents"] is not None:
        agents = [a for a in agents if a.agent_id in cfg["agents"]]
    return Orchestrator(
        agents=agents,
        correlator=Correlator(corroboration=cfg["corroboration"]),
        courtroom=cfg["courtroom"],
    )


def run_one(job: dict[str, Any]) -> dict[str, Any]:
    """Worker: one configuration on one run (optionally mutated first)."""
    from netcoop.mutation import MUTATORS, NotApplicable, mutate
    from netcoop.protocol.common import EntityRole, MessageType

    src = Path(job["run"])
    gt = json.loads((src / META_FILE).read_text(encoding="utf-8"))["ground_truth"]
    tmp: Path | None = None
    path: Path = src
    applied: list[str] = []
    if job.get("mutations"):
        tmp = Path(tempfile.mkdtemp(prefix="netcoop-eval-"))
        rng = random.Random(f"{src.name}:{job['mutations']}")
        kinds = rng.sample(sorted(MUTATORS), len(MUTATORS))
        current = src
        for kind in kinds:
            if len(applied) == job["mutations"]:
                break
            dst = tmp / f"m{len(applied)}"
            try:
                mutate(current, dst, kind, seed=len(applied))
            except NotApplicable:
                continue
            applied.append(kind)
            current = dst
        path = current
    try:
        res = _orchestrator(job["config"]).run(path)
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
    verdicts = res.board.query(type=MessageType.VERDICT)
    prelim, final = verdicts[0].payload, verdicts[-1].payload

    def root_of(entities: Any) -> str | None:
        return next((e.entity.entity_id for e in entities if e.role is EntityRole.ROOT), None)

    return {
        "run": src.name,
        "config": job["config"]["name"],
        "mutations": applied,
        "family": gt["scenario"],
        "root_cause": gt["root_cause"],
        "locations": sorted(truth_locations(gt)),
        "truth_affected": sorted(gt.get("affected_entities") or []),
        "intensity": gt["intensity"],
        "noise": gt["noise"],
        "missing_rate": gt["missing_rate"],
        "status": res.report.status.value,
        "claimed_type": final.hypothesis_type,
        "claimed_root": root_of(final.entities),
        "affected": list(res.report.affected_devices),
        "confidence": res.report.confidence,
        "ranking": [[r.hypothesis_type, root_of(r.entities), r.confidence] for r in prelim.ranking],
        "courtroom": final.method == "courtroom",
        "errors": len(res.board.query(type=MessageType.ERROR)),
    }


def run_jobs(jobs: list[dict[str, Any]], workers: int) -> list[dict[str, Any]]:
    with cf.ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(run_one, jobs, chunksize=4))


def runs_under(root: Path) -> list[Path]:
    return (
        sorted(
            d
            for fam in sorted(root.iterdir())
            if fam.is_dir()
            for d in sorted(fam.iterdir())
            if (d / META_FILE).is_file()
        )
        if root.is_dir()
        else []
    )
