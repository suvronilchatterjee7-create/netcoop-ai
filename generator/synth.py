"""Provisional stand-in for the organiser's synthetic telemetry generator (D-004).

Simulates a three-tier campus network (core router, per-zone distribution and
access switches, access points, DNS/DHCP servers) and injects one fault family
with a configurable intensity, noise and missing-data rate. Parameters come from
``config/synthetic_generator.yaml``.

Two output dialects exercise the Translator:

* ``netcoop_synth_v2``: ``topology.json`` + ``telemetry.jsonl`` (ISO timestamps,
  ms / % units, one record per entity per interval with a ``kind`` field).
* ``legacy_v1``: one CSV per record kind, different field names, epoch-second
  timestamps, ratio (0-1) instead of percent, microseconds / seconds / kbit/s,
  upper-case enums, and links identified by endpoint pair instead of ID.

The legacy dialect is only used for the ``interop_failure`` family, layered on
top of an underlying network state drawn from ``interop.underlying_faults``.
This module is a data source only; nothing in ``netcoop/`` imports it.
"""

from __future__ import annotations

import csv
import json
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from netcoop.config import get_value, load_config

NATIVE = "netcoop_synth_v2"
LEGACY = "legacy_v1"


@dataclass(frozen=True)
class Node:
    id: str
    type: str
    tier: str
    zone: str
    parent: str | None


@dataclass(frozen=True)
class Link:
    id: str
    a: str
    b: str
    tier: str
    capacity_mbps: float


@dataclass
class Topology:
    nodes: dict[str, Node] = field(default_factory=dict)
    links: list[Link] = field(default_factory=list)

    def subtree(self, root: str) -> set[str]:
        out, frontier = {root}, [root]
        while frontier:
            cur = frontier.pop()
            for n in self.nodes.values():
                if n.parent == cur and n.id not in out:
                    out.add(n.id)
                    frontier.append(n.id)
        return out

    def vantages(self) -> list[str]:
        return [n.id for n in self.nodes.values() if n.tier in ("access", "edge")]


class Synth:
    def __init__(self, rng: np.random.Generator) -> None:
        self.cfg = load_config("synthetic_generator")
        self.rng = rng
        self.T = int(self.p("time.n_steps"))
        self.t = np.arange(self.T)

    def p(self, key: str) -> Any:
        return get_value(self.cfg, key)

    # ------------------------------------------------------------------ topology
    def build_topology(self) -> Topology:
        topo = Topology()

        def add(node: Node) -> None:
            topo.nodes[node.id] = node
            if node.parent is not None:
                cap = float(self.p(f"topology.capacity_mbps.{node.tier}"))
                topo.links.append(
                    Link(f"{node.parent}--{node.id}", node.parent, node.id, node.tier, cap)
                )

        core = Node("core-rtr-01", "router", "core", "core", None)
        add(core)
        for svc in self.p("topology.services"):
            add(Node(f"{svc}-srv-01", "server", "service", "core", core.id))
        acc_lo, acc_hi = self.p("topology.access_switches_per_zone")
        ap_lo, ap_hi = self.p("topology.aps_per_access_switch")
        for zone in self.p("topology.zones"):
            dist = Node(f"{zone}-dist-01", "switch", "distribution", zone, core.id)
            add(dist)
            for i in range(int(self.rng.integers(acc_lo, acc_hi + 1))):
                acc = Node(f"{zone}-acc-{i + 1:02d}", "switch", "access", zone, dist.id)
                add(acc)
                for j in range(int(self.rng.integers(ap_lo, ap_hi + 1))):
                    add(Node(f"{acc.id}-ap-{j + 1:02d}", "access_point", "edge", zone, acc.id))
        return topo

    # ------------------------------------------------------------------ series
    def ar1(self, mean: float, sd: float) -> np.ndarray:
        phi = float(self.p("baseline.ar1_phi"))
        e = self.rng.normal(0.0, sd * np.sqrt(1 - phi**2), self.T)
        x = np.empty(self.T)
        x[0] = self.rng.normal(0.0, sd)
        for k in range(1, self.T):
            x[k] = phi * x[k - 1] + e[k]
        return mean + x

    def ramp(self, intensity: float) -> np.ndarray:
        onset = int(self.p("time.onset_fraction") * self.T)
        steps = float(self.p("time.ramp_steps"))
        return intensity * np.clip((self.t - onset + 1) / steps, 0.0, 1.0)

    def baseline(self, topo: Topology) -> dict[str, Any]:
        links: dict[str, dict[str, np.ndarray]] = {}
        for ln in topo.links:
            links[ln.id] = {
                "latency_ms": self.ar1(*self.p("baseline.link.latency_ms")),
                "jitter_ms": self.ar1(*self.p("baseline.link.jitter_ms")),
                "loss_pct": self.ar1(*self.p("baseline.link.loss_pct")),
                "utilization_pct": self.ar1(*self.p(f"baseline.link.utilization_pct.{ln.tier}")),
            }
        devices: dict[str, dict[str, Any]] = {}
        for n in topo.nodes.values():
            devices[n.id] = {
                "cpu_pct": self.ar1(*self.p("baseline.device.cpu_pct")),
                "mem_pct": self.ar1(*self.p("baseline.device.mem_pct")),
                "queue_lam": np.full(self.T, float(self.p("baseline.device.queue_drops_rate"))),
                "in_err_lam": np.full(self.T, float(self.p("baseline.device.if_errors_rate"))),
                "out_err_lam": np.full(self.T, float(self.p("baseline.device.if_errors_rate"))),
                "status": np.array(["up"] * self.T, dtype=object),
            }
        wireless: dict[str, dict[str, np.ndarray]] = {}
        for n in topo.nodes.values():
            if n.type == "access_point":
                wireless[n.id] = {
                    k: self.ar1(*self.p(f"baseline.wireless.{k}"))
                    for k in ("rssi_dbm", "snr_db", "retrans_pct", "loss_pct", "clients")
                }
        service: dict[tuple[str, str], dict[str, np.ndarray]] = {}
        for svc in self.p("topology.services"):
            for v in topo.vantages():
                service[(svc, v)] = {
                    "success_pct": self.ar1(*self.p("baseline.service.success_pct")),
                    "response_ms": self.ar1(*self.p("baseline.service.response_ms")),
                }
        return {"links": links, "devices": devices, "wireless": wireless, "service": service}

    # ------------------------------------------------------------------ faults
    def inject(
        self, family: str, topo: Topology, m: dict[str, Any], intensity: float
    ) -> dict[str, Any]:
        r = self.ramp(intensity)
        f = f"faults.{family}"
        if family == "normal":
            return {"target_entity": None, "affected_entities": []}
        if family == "link_congestion":
            tiers = self.p(f"{f}.target_tiers")
            ln = self._choice([x for x in topo.links if x.tier in tiers])
            lm = m["links"][ln.id]
            lm["utilization_pct"] += r * (self.p(f"{f}.utilization_pct") - lm["utilization_pct"])
            lm["latency_ms"] += r * self.p(f"{f}.latency_add_ms")
            lm["jitter_ms"] += r * self.p(f"{f}.jitter_add_ms")
            lm["loss_pct"] += r * self.p(f"{f}.loss_add_pct")
            m["devices"][ln.a]["queue_lam"] *= 1 + r * self.p(f"{f}.queue_drop_multiplier")
            self._slow_services(topo.subtree(ln.b), m, r * self.p(f"{f}.service_response_add_ms"))
            return {"target_entity": ln.id, "affected_entities": [ln.id, ln.a, ln.b]}
        if family == "weak_wifi":
            ap = self._choice(sorted(m["wireless"]))
            w = m["wireless"][ap]
            w["rssi_dbm"] -= r * self.p(f"{f}.rssi_drop_db")
            w["snr_db"] -= r * self.p(f"{f}.snr_drop_db")
            w["retrans_pct"] += r * self.p(f"{f}.retrans_add_pct")
            w["loss_pct"] += r * self.p(f"{f}.loss_add_pct")
            self._slow_services({ap}, m, r * self.p(f"{f}.service_response_add_ms"))
            return {"target_entity": ap, "affected_entities": [ap]}
        if family == "interface_fault":
            tiers = self.p(f"{f}.target_tiers")
            ln = self._choice([x for x in topo.links if x.tier in tiers])
            onset_rel = np.clip(self.t - int(self.p("time.onset_fraction") * self.T) + 1, 0, None)
            d = m["devices"][ln.b]
            d["in_err_lam"] += (r > 0) * intensity * self.p(f"{f}.error_rate_slope") * onset_rel
            lm = m["links"][ln.id]
            lm["loss_pct"] += r * self.p(f"{f}.loss_add_pct")
            flaps = self.rng.random(self.T) < r * self.p(f"{f}.flap_probability")
            d["status"][flaps] = "down"
            d["status"][(r > 0) & ~flaps] = "degraded"
            lm["loss_pct"][flaps] = 100.0
            lm["utilization_pct"][flaps] = 0.0
            return {"target_entity": ln.id, "affected_entities": [ln.id, ln.b]}
        if family == "dns_dhcp_failure":
            svc = self._choice(list(self.p("topology.services")))
            for (s, _v), sm in m["service"].items():
                if s == svc:
                    sm["success_pct"] -= r * (sm["success_pct"] - self.p(f"{f}.failed_success_pct"))
                    sm["response_ms"] += r * self.p(f"{f}.response_add_ms")
            server = f"{svc}-srv-01"
            return {"target_entity": server, "affected_entities": [server], "service": svc}
        if family == "hardware_failure":
            tiers = self.p(f"{f}.target_tiers")
            devices = [n.id for n in topo.nodes.values() if n.tier in tiers and n.type != "server"]
            dev = self._choice(devices)
            attached = [ln for ln in topo.links if dev in (ln.a, ln.b)]
            down = self.rng.random(self.T) < r * self.p(f"{f}.down_probability")
            d = m["devices"][dev]
            d["status"][down] = "down"
            d["status"][(r > 0) & ~down] = "degraded"
            d["in_err_lam"] += r * self.p(f"{f}.error_rate")
            for ln in attached:
                lm = m["links"][ln.id]
                lm["loss_pct"] += r * self.p(f"{f}.loss_add_pct")
                lm["loss_pct"][down] = 100.0
                lm["utilization_pct"][down] = 0.0
            return {"target_entity": dev, "affected_entities": [dev, *(ln.id for ln in attached)]}
        if family == "device_overload":
            tiers = self.p(f"{f}.target_tiers")
            dev = self._choice([n.id for n in topo.nodes.values() if n.tier in tiers])
            d = m["devices"][dev]
            d["cpu_pct"] += r * (self.p(f"{f}.cpu_pct") - d["cpu_pct"])
            d["mem_pct"] += r * self.p(f"{f}.mem_add_pct")
            d["queue_lam"] *= 1 + r * self.p(f"{f}.queue_drop_multiplier")
            for ln in topo.links:
                if dev in (ln.a, ln.b):
                    m["links"][ln.id]["latency_ms"] += r * self.p(f"{f}.latency_add_ms")
            return {"target_entity": dev, "affected_entities": [dev]}
        raise ValueError(f"unknown fault family {family!r}")

    def _choice(self, items: list[Any]) -> Any:
        return items[int(self.rng.integers(0, len(items)))]

    @staticmethod
    def _slow_services(vantages: set[str], m: dict[str, Any], add: np.ndarray) -> None:
        for (_s, v), sm in m["service"].items():
            if v in vantages:
                sm["response_ms"] += add

    # ------------------------------------------------------------------ noise
    def finalize(self, m: dict[str, Any], noise: float) -> None:
        pct_lo, pct_hi = self.p("bounds.pct")

        def jitter(x: np.ndarray) -> np.ndarray:
            return x + noise * np.abs(x) * self.rng.normal(0.0, 1.0, x.shape)

        for lm in m["links"].values():
            for k in lm:
                lm[k] = jitter(lm[k])
                lm[k] = (
                    np.clip(lm[k], pct_lo, pct_hi)
                    if k.endswith("_pct")
                    else np.clip(lm[k], 0, None)
                )
        for d in m["devices"].values():
            for k in ("cpu_pct", "mem_pct"):
                d[k] = np.clip(jitter(d[k]), pct_lo, pct_hi)
            for lam, out in (
                ("queue_lam", "queue_drops"),
                ("in_err_lam", "if_in_errors"),
                ("out_err_lam", "if_out_errors"),
            ):
                d[out] = self.rng.poisson(np.clip(jitter(d.pop(lam)), 0, None))
        for w in m["wireless"].values():
            for k in w:
                w[k] = jitter(w[k])
            w["rssi_dbm"] = np.clip(w["rssi_dbm"], *self.p("bounds.rssi_dbm"))
            w["snr_db"] = np.clip(w["snr_db"], *self.p("bounds.snr_db"))
            for k in ("retrans_pct", "loss_pct"):
                w[k] = np.clip(w[k], pct_lo, pct_hi)
            w["clients"] = np.clip(np.rint(w["clients"]), 0, None).astype(int)
        for sm in m["service"].values():
            sm["success_pct"] = np.clip(jitter(sm["success_pct"]), pct_lo, pct_hi)
            sm["response_ms"] = np.clip(jitter(sm["response_ms"]), 0, None)

    # ------------------------------------------------------------------ records
    def timestamps(self) -> list[datetime]:
        start = datetime.fromisoformat(str(self.p("time.start_utc")).replace("Z", "+00:00"))
        step = timedelta(seconds=float(self.p("time.interval_s")))
        return [start + k * step for k in range(self.T)]

    def records(self, topo: Topology, m: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        link_by_id = {ln.id: ln for ln in topo.links}
        for k, ts in enumerate(self.timestamps()):
            iso = ts.isoformat().replace("+00:00", "Z")
            for lid, lm in m["links"].items():
                cap = link_by_id[lid].capacity_mbps
                rows.append(
                    {
                        "ts": iso,
                        "kind": "link",
                        "link_id": lid,
                        **{x: float(lm[x][k]) for x in lm},
                        "throughput_mbps": float(lm["utilization_pct"][k]) / 100 * cap,
                    }
                )
            for did, d in m["devices"].items():
                rows.append(
                    {
                        "ts": iso,
                        "kind": "device",
                        "device_id": did,
                        "status": str(d["status"][k]),
                        "cpu_pct": float(d["cpu_pct"][k]),
                        "mem_pct": float(d["mem_pct"][k]),
                        "egress_queue_drops": int(d["queue_drops"][k]),
                        "if_in_errors": int(d["if_in_errors"][k]),
                        "if_out_errors": int(d["if_out_errors"][k]),
                    }
                )
            for ap, w in m["wireless"].items():
                rows.append(
                    {
                        "ts": iso,
                        "kind": "wireless",
                        "ap_id": ap,
                        **{x: (int(w[x][k]) if x == "clients" else float(w[x][k])) for x in w},
                    }
                )
            for (svc, v), sm in m["service"].items():
                rows.append(
                    {
                        "ts": iso,
                        "kind": "service",
                        "service": svc,
                        "vantage_id": v,
                        "server_id": f"{svc}-srv-01",
                        "success_pct": float(sm["success_pct"][k]),
                        "response_ms": float(sm["response_ms"][k]),
                    }
                )
        return rows

    def degrade(self, rows: list[dict[str, Any]], missing: float) -> list[dict[str, Any]]:
        keys = {"ts", "kind", "link_id", "device_id", "ap_id", "service", "vantage_id"}
        p_field = missing * float(self.p("noise.field_drop_ratio"))
        out = []
        for row in rows:
            if self.rng.random() < missing:
                continue
            out.append({k: v for k, v in row.items() if k in keys or self.rng.random() >= p_field})
        return out


# ---------------------------------------------------------------------- writers
def _round(v: Any) -> Any:
    return round(v, 3) if isinstance(v, float) else v


def write_native(out_dir: Path, topo: Topology, rows: list[dict[str, Any]]) -> list[Path]:
    tp = out_dir / "topology.json"
    tp.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "nodes": [
                    {"id": n.id, "type": n.type, "tier": n.tier, "zone": n.zone, "parent": n.parent}
                    for n in topo.nodes.values()
                ],
                "links": [
                    {"id": ln.id, "a": ln.a, "b": ln.b, "capacity_mbps": ln.capacity_mbps}
                    for ln in topo.links
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    te = out_dir / "telemetry.jsonl"
    with te.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(
                json.dumps({"schema_version": "2.0", **{k: _round(v) for k, v in row.items()}})
                + "\n"
            )
    return [tp, te]


_LEGACY_TYPE = {"router": "RTR", "switch": "SW", "access_point": "AP", "server": "SRV"}


def _legacy_row(row: dict[str, Any], links: dict[str, Link]) -> tuple[str, dict[str, Any]]:
    epoch = int(datetime.fromisoformat(row["ts"].replace("Z", "+00:00")).timestamp())
    g = row.get
    kind = row["kind"]

    def scale(key: str, factor: float) -> Any:
        v = g(key)
        return None if v is None else v * factor

    if kind == "link":
        ln = links[row["link_id"]]
        return "link_stats.csv", {
            "time": epoch,
            "src": ln.a,
            "dst": ln.b,
            "latency_us": scale("latency_ms", 1000),
            "jitter_us": scale("jitter_ms", 1000),
            "loss_ratio": scale("loss_pct", 0.01),
            "util_ratio": scale("utilization_pct", 0.01),
            "tput_kbps": scale("throughput_mbps", 1000),
        }
    if kind == "device":
        st = g("status")
        return "device_stats.csv", {
            "time": epoch,
            "hostname": row["device_id"],
            "state": None if st is None else st.upper(),
            "cpu_load": scale("cpu_pct", 0.01),
            "mem_used_ratio": scale("mem_pct", 0.01),
            "q_drops": g("egress_queue_drops"),
            "rx_errs": g("if_in_errors"),
            "tx_errs": g("if_out_errors"),
        }
    if kind == "wireless":
        return "wifi_stats.csv", {
            "time": epoch,
            "ap": row["ap_id"],
            "signal": g("rssi_dbm"),
            "snr": g("snr_db"),
            "retry_ratio": scale("retrans_pct", 0.01),
            "loss_ratio": scale("loss_pct", 0.01),
            "stations": g("clients"),
        }
    return "service_checks.csv", {
        "time": epoch,
        "svc": row["service"].upper(),
        "vantage": row["vantage_id"],
        "ok_ratio": scale("success_pct", 0.01),
        "resp_time_s": scale("response_ms", 0.001),
    }


def write_legacy(out_dir: Path, topo: Topology, rows: list[dict[str, Any]]) -> list[Path]:
    paths: list[Path] = []
    tp = out_dir / "topology_edges.csv"
    with tp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["parent", "child", "child_type", "uplink_kbps"])
        for ln in topo.links:
            w.writerow(
                [ln.a, ln.b, _LEGACY_TYPE[topo.nodes[ln.b].type], int(ln.capacity_mbps * 1000)]
            )
    paths.append(tp)
    links = {ln.id: ln for ln in topo.links}
    tables: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        name, rec = _legacy_row(row, links)
        tables.setdefault(name, []).append(rec)
    for name, recs in sorted(tables.items()):
        p = out_dir / name
        with p.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["schema_ver", *recs[0].keys()])
            w.writeheader()
            for rec in recs:
                w.writerow(
                    {
                        "schema_ver": "1.0",
                        **{k: ("" if v is None else _round(v)) for k, v in rec.items()},
                    }
                )
        paths.append(p)
    return paths


def generate(
    scenario: str, seed: int, intensity: float, noise: float, missing_rate: float, out_dir: Path
) -> list[Path]:
    """Generate one run. Writes data files plus ``ground_truth.json``."""
    ss = np.random.SeedSequence(
        [
            seed,
            zlib.crc32(scenario.encode()),
            int(intensity * 1000),
            int(noise * 1000),
            int(missing_rate * 1000),
        ]
    )
    synth = Synth(np.random.default_rng(ss))
    topo = synth.build_topology()
    metrics = synth.baseline(topo)
    dialect = NATIVE
    underlying = scenario
    if scenario == "interop_failure":
        dialect = LEGACY
        underlying = synth._choice(list(synth.p("interop.underlying_faults")))
    truth = synth.inject(underlying, topo, metrics, intensity)
    synth.finalize(metrics, noise)
    rows = synth.degrade(synth.records(topo, metrics), missing_rate)
    files = (
        write_native(out_dir, topo, rows)
        if dialect == NATIVE
        else write_legacy(out_dir, topo, rows)
    )
    onset_idx = int(synth.p("time.onset_fraction") * synth.T)
    gt = {
        "scenario": scenario,
        "root_cause": underlying,
        "dialect": dialect,
        "onset_ts": synth.timestamps()[onset_idx].isoformat().replace("+00:00", "Z"),
        **truth,
    }
    gp = out_dir / "ground_truth.json"
    gp.write_text(json.dumps(gt, indent=2), encoding="utf-8")
    return [*files, gp]
