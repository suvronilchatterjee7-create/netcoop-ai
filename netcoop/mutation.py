"""Interop-failure mutator: systematically corrupt valid generated runs (Phase 2, task 7).

Each mutation copies a run directory, applies one well-defined change to its files and
returns a ``Mutation`` record saying what the Translator must do with it:

* ``values="all"``        - recoverable: every canonical series must equal the original
* ``values="unaffected"`` - partly lossy: series not touched must equal the original,
                            touched ones may be missing or shortened
* ``values="flagged"``    - inherently ambiguous: values may differ, but the affected
                            series must carry the expected issue in their quality record
* ``expect_codes``        - typed ERROR codes that must be reported

The mutator is generic: it finds metric/timestamp/entity fields through the same
declarative mapping the Translator uses, so it works on any dialect.
"""

from __future__ import annotations

import csv
import json
import random
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from netcoop.generation import LABEL_FILES
from netcoop.protocol.common import ErrorCode
from netcoop.translator.issues import IssueLog
from netcoop.translator.mapping import Mapping, get_mapping, normalise_key
from netcoop.translator.readers import RawTable, read_path
from netcoop.translator.topology import is_topology_table

Values = Literal["all", "unaffected", "flagged"]


@dataclass
class Mutation:
    kind: str
    file: str
    detail: str
    values: Values
    expect_codes: frozenset[ErrorCode] = frozenset()
    affected_entities: frozenset[str] = frozenset()
    affected_metrics: frozenset[str] = frozenset()  # canonical metric names
    ignore_time: bool = False  # compare values only (timestamps were shifted on purpose)
    renamed_entities: dict[str, str] = field(default_factory=dict)
    flag_issue: str | None = None


class NotApplicable(Exception):
    """The mutation has nothing to act on in this run (e.g. single-file run)."""


@dataclass
class _File:
    path: Path
    fmt: str
    records: list[dict[str, Any]]


class _Run:
    def __init__(self, root: Path, mapping: Mapping) -> None:
        self.root = root
        self.mapping = mapping
        self.telemetry: list[_File] = []
        self.topology_files: list[Path] = []
        for p in sorted(root.iterdir()):
            if p.name in LABEL_FILES or not p.is_file():
                continue
            tables: list[RawTable] = read_path(p, IssueLog())
            if any(is_topology_table(t, mapping) for t in tables):
                self.topology_files.append(p)
            elif tables:
                self.telemetry.append(_File(p, tables[0].fmt, [r for _, r in tables[0].records]))

    def save(self, f: _File) -> None:
        if f.fmt == "csv":
            cols = list(dict.fromkeys(k for r in f.records for k in r))
            with f.path.open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=cols)
                w.writeheader()
                w.writerows(f.records)
        else:
            f.path.write_text("".join(json.dumps(r) + "\n" for r in f.records), encoding="utf-8")

    # -- field discovery -------------------------------------------------------------
    def keys(self, f: _File) -> list[str]:
        return list(dict.fromkeys(k for r in f.records for k in r))

    def metric_fields(
        self, f: _File, unambiguous: bool = True
    ) -> list[tuple[str, str, str | None]]:
        """(field, metric, declared unit) for metric fields of a file."""
        out = []
        for k in self.keys(f):
            aliases = self.mapping.metric_aliases.get(normalise_key(k), ())
            if aliases and (len(aliases) == 1 or not unambiguous):
                out.append((k, aliases[0].metric, aliases[0].unit))
        return out

    def ts_field(self, f: _File) -> str:
        return next(k for k in self.keys(f) if normalise_key(k) in self.mapping.timestamp_fields)

    def id_fields(self, f: _File) -> list[str]:
        ids = set()
        for b in self.mapping.bindings:
            ids |= set(b.id_fields) | {x for p in b.endpoint_fields for x in p}
        return [k for k in self.keys(f) if normalise_key(k) in ids]

    def _placed_bindings(self) -> list[Any]:
        """Bindings whose entities live in the topology (services are not topology nodes)."""
        return [b for b in self.mapping.bindings if b.entity_type != "service"]

    def has_entity_field(self, f: _File) -> bool:
        keys = {normalise_key(k) for k in self.keys(f)}
        return any(keys & set(b.id_fields) for b in self._placed_bindings())

    def entity_field(self, f: _File) -> str:
        for b in self._placed_bindings():
            for k in self.keys(f):
                if normalise_key(k) in b.id_fields:
                    return k
        raise NotApplicable("no single-field entity id")

    def record_entities(self, r: dict[str, Any]) -> set[str]:
        """Every entity id a record could map to (id fields, vantage points, endpoint links)."""
        out: set[str] = set()
        norm = {normalise_key(k): v for k, v in r.items()}
        for b in self.mapping.bindings:
            for k in (*b.id_fields, *b.observed_from_fields):
                if norm.get(k) not in (None, ""):
                    out |= {str(norm[k]), str(norm[k]).lower()}
            for a, z in b.endpoint_fields:
                if norm.get(a) not in (None, "") and norm.get(z) not in (None, ""):
                    out.add(
                        str(self.mapping.topology["link_id_template"]).format(a=norm[a], b=norm[z])
                    )
        return out


def _num(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _fmt_like(original: Any, value: float) -> Any:
    return repr(value) if isinstance(original, str) else value


# Shifts large enough to exceed any staleness/skew tolerance for minute-level polling.
STALE_SHIFT = timedelta(hours=6)
FILE_SHIFT = timedelta(hours=3)


def _shift(ts: Any, delta: timedelta) -> Any:
    """Shift a timestamp back by ``delta``, keeping its form (ISO / epoch s / epoch ms)."""
    v = _num(ts)
    if v is None:
        return (datetime.fromisoformat(str(ts).replace("Z", "+00:00")) - delta).isoformat()
    scale = 1000 if abs(v) >= 1e11 else 1
    shifted = v - delta.total_seconds() * scale
    return (
        _fmt_like(ts, shifted)
        if isinstance(ts, str)
        else (int(shifted) if isinstance(ts, int) else shifted)
    )


Mutator = Callable[[_Run, random.Random], Mutation]
MUTATORS: dict[str, Mutator] = {}


def mutator(name: str) -> Callable[[Mutator], Mutator]:
    def reg(fn: Mutator) -> Mutator:
        MUTATORS[name] = fn
        return fn

    return reg


def _pick_file(
    run: _Run, rng: random.Random, pred: Callable[[_File], bool] = lambda f: True
) -> _File:
    files = [f for f in run.telemetry if pred(f)]
    if not files:
        raise NotApplicable("no suitable telemetry file")
    return files[rng.randrange(len(files))]


def _rename(f: _File, old: str, new: str) -> None:
    f.records = [{(new if k == old else k): v for k, v in r.items()} for r in f.records]


# ----------------------------------------------------------------------------- recoverable
@mutator("rename_case")
def _rename_case(run: _Run, rng: random.Random) -> Mutation:
    f = _pick_file(run, rng, lambda f: bool(run.metric_fields(f)))
    k, metric, _ = rng.choice(run.metric_fields(f))
    new = "-".join(
        part.upper() if i % 2 else part.capitalize() for i, part in enumerate(k.split("_"))
    )
    _rename(f, k, new)
    run.save(f)
    return Mutation("rename_case", f.path.name, f"{k} -> {new}", "all")


@mutator("rename_alias")
def _rename_alias(run: _Run, rng: random.Random) -> Mutation:
    m = run.mapping
    for f in rng.sample(run.telemetry, len(run.telemetry)):
        present = {normalise_key(k) for k in run.keys(f)}
        options = []
        for k, metric, unit in run.metric_fields(f):
            for alias, cands in m.metric_aliases.items():
                if (
                    alias not in present
                    and len(cands) == 1
                    and cands[0].metric == metric
                    and cands[0].unit == unit
                    and unit is not None
                ):
                    options.append((k, alias, metric))
        if options:
            k, alias, metric = rng.choice(options)
            _rename(f, k, alias)
            run.save(f)
            return Mutation("rename_alias", f.path.name, f"{k} -> {alias}", "all")
    raise NotApplicable("no alternative alias")


@mutator("unit_change")
def _unit_change(run: _Run, rng: random.Random) -> Mutation:
    m = run.mapping
    for f in rng.sample(run.telemetry, len(run.telemetry)):
        present = {normalise_key(k) for k in run.keys(f)}
        options = []
        for k, metric, unit in run.metric_fields(f):
            u1 = m.unit(unit)
            if u1 is None:
                continue
            for alias, cands in m.metric_aliases.items():
                u2 = m.unit(cands[0].unit) if len(cands) == 1 else None
                if (
                    alias not in present
                    and cands[0].metric == metric
                    and u2 is not None
                    and u2.dimension == u1.dimension
                    and u2.factor != u1.factor
                ):
                    options.append((k, alias, u1.factor / u2.factor, f"{u1.name}->{u2.name}"))
        if options:
            k, alias, factor, desc = rng.choice(options)
            for r in f.records:
                if k in r:
                    v = _num(r[k])
                    r[alias] = _fmt_like(r[k], v * factor) if v is not None else r[k]
                    del r[k]
            run.save(f)
            return Mutation("unit_change", f.path.name, f"{k} -> {alias} ({desc})", "all")
    raise NotApplicable("no convertible unit")


@mutator("timestamp_format")
def _timestamp_format(run: _Run, rng: random.Random) -> Mutation:
    f = _pick_file(run, rng)
    k = run.ts_field(f)
    sample = next(r[k] for r in f.records if k in r)
    to_epoch = _num(sample) is None
    for r in f.records:
        if k not in r:
            continue
        if to_epoch:
            dt = datetime.fromisoformat(str(r[k]).replace("Z", "+00:00"))
            r[k] = _fmt_like(r[k], dt.timestamp()) if f.fmt == "csv" else int(dt.timestamp() * 1000)
        else:
            r[k] = datetime.fromtimestamp(float(r[k]), tz=UTC).isoformat()
    run.save(f)
    return Mutation(
        "timestamp_format", f.path.name, f"{k}: {'ISO->epoch' if to_epoch else 'epoch->ISO'}", "all"
    )


@mutator("enum_case")
def _enum_case(run: _Run, rng: random.Random) -> Mutation:
    for f in rng.sample(run.telemetry, len(run.telemetry)):
        enum_fields = [
            k for k, metric, _ in run.metric_fields(f) if metric in run.mapping.enum_values
        ]
        if enum_fields:
            k = rng.choice(enum_fields)
            for r in f.records:
                if k in r:
                    r[k] = str(r[k]).swapcase()
            run.save(f)
            return Mutation("enum_case", f.path.name, f"{k} values case-swapped", "all")
    raise NotApplicable("no enum field")


@mutator("schema_version_change")
def _schema_version(run: _Run, rng: random.Random) -> Mutation:
    for f in rng.sample(run.telemetry, len(run.telemetry)):
        ks = [k for k in run.keys(f) if normalise_key(k) in run.mapping.schema_version_fields]
        if ks:
            for r in f.records:
                r[ks[0]] = "9.9"
            run.save(f)
            return Mutation(
                "schema_version_change",
                f.path.name,
                f"{ks[0]} = 9.9",
                "all",
                frozenset({ErrorCode.INCOMPATIBLE_SCHEMA}),
            )
    raise NotApplicable("no schema version field")


@mutator("unknown_extra_field")
def _extra_field(run: _Run, rng: random.Random) -> Mutation:
    f = _pick_file(run, rng)
    for i, r in enumerate(f.records):
        r["vendor_opaque_counter"] = i
    run.save(f)
    return Mutation(
        "unknown_extra_field",
        f.path.name,
        "added vendor_opaque_counter",
        "all",
        frozenset({ErrorCode.UNKNOWN_FIELD}),
    )


@mutator("shuffle_records")
def _shuffle(run: _Run, rng: random.Random) -> Mutation:
    f = _pick_file(run, rng)
    rng.shuffle(f.records)
    run.save(f)
    return Mutation("shuffle_records", f.path.name, "record order shuffled", "all")


@mutator("duplicate_records")
def _duplicate(run: _Run, rng: random.Random) -> Mutation:
    f = _pick_file(run, rng)
    idx = sorted(rng.sample(range(len(f.records)), max(1, len(f.records) // 10)))
    for i in reversed(idx):
        f.records.insert(i, dict(f.records[i]))
    run.save(f)
    return Mutation(
        "duplicate_records",
        f.path.name,
        f"{len(idx)} records duplicated",
        "all",
        frozenset({ErrorCode.DUPLICATE_SAMPLE}),
    )


@mutator("drop_topology")
def _drop_topology(run: _Run, rng: random.Random) -> Mutation:
    if not run.topology_files:
        raise NotApplicable("no topology file")
    for p in run.topology_files:
        p.unlink()
    return Mutation(
        "drop_topology",
        ",".join(p.name for p in run.topology_files),
        "topology removed",
        "all",
        frozenset({ErrorCode.MISSING_TOPOLOGY}),
    )


# ----------------------------------------------------------------------------- ambiguous
@mutator("drop_unit_suffix")
def _drop_unit(run: _Run, rng: random.Random) -> Mutation:
    m = run.mapping
    for f in rng.sample(run.telemetry, len(run.telemetry)):
        present = {normalise_key(k) for k in run.keys(f)}
        options = []
        for k, metric, unit in run.metric_fields(f):
            info = m.unit(unit)
            # only dimensions with several units are genuinely ambiguous without a unit
            if (
                info is None
                or len({u.name for u in m.units.values() if u.dimension == info.dimension}) < 2
            ):
                continue
            for alias, cands in m.metric_aliases.items():
                if (
                    alias not in present
                    and len(cands) == 1
                    and cands[0].metric == metric
                    and cands[0].unit is None
                    and m.unit_from_suffix(alias, info.dimension) is None
                ):
                    options.append((k, alias, metric))
        if options:
            k, alias, metric = rng.choice(options)
            _rename(f, k, alias)
            run.save(f)
            return Mutation(
                "drop_unit_suffix",
                f.path.name,
                f"{k} -> {alias} (unit removed)",
                "flagged",
                frozenset({ErrorCode.AMBIGUOUS_UNIT}),
                affected_metrics=frozenset({metric}),
                flag_issue=ErrorCode.AMBIGUOUS_UNIT.value,
            )
    raise NotApplicable("no unit-bearing field with a unit-less alias")


# ----------------------------------------------------------------------------- degraded but usable
@mutator("stale_entity")
def _stale_entity(run: _Run, rng: random.Random) -> Mutation:
    f = _pick_file(run, rng, run.has_entity_field)
    k, ek = run.ts_field(f), run.entity_field(f)
    target = rng.choice(sorted({str(r[ek]) for r in f.records if ek in r}))
    for r in f.records:
        if str(r.get(ek)) == target and k in r:
            r[k] = _shift(r[k], STALE_SHIFT)
    run.save(f)
    return Mutation(
        "stale_entity",
        f.path.name,
        f"{target} records shifted back {STALE_SHIFT}",
        "all",
        frozenset({ErrorCode.STALE_DATA}),
        affected_entities=frozenset({target}),
        ignore_time=True,
        flag_issue=ErrorCode.STALE_DATA.value,
    )


@mutator("file_time_shift")
def _file_shift(run: _Run, rng: random.Random) -> Mutation:
    if len(run.telemetry) < 2:
        raise NotApplicable("needs several telemetry sources to detect a shifted one")
    f = _pick_file(run, rng)
    k = run.ts_field(f)
    for r in f.records:
        if k in r:
            r[k] = _shift(r[k], FILE_SHIFT)
    run.save(f)
    return Mutation(
        "file_time_shift",
        f.path.name,
        f"whole file shifted back {FILE_SHIFT}",
        "all",
        frozenset({ErrorCode.CLOCK_SKEW, ErrorCode.STALE_DATA}),
        ignore_time=True,
    )


@mutator("unknown_devices")
def _unknown_devices(run: _Run, rng: random.Random) -> Mutation:
    f = _pick_file(run, rng, run.has_entity_field)
    ek = run.entity_field(f)
    target = rng.choice(sorted({str(r[ek]) for r in f.records if ek in r}))
    ghost = f"ghost-{target}"
    for r in f.records:
        if str(r.get(ek)) == target:
            r[ek] = ghost
    run.save(f)
    return Mutation(
        "unknown_devices",
        f.path.name,
        f"{target} -> {ghost}",
        "all",
        frozenset({ErrorCode.UNKNOWN_ENTITY}),
        renamed_entities={target: ghost},
        flag_issue=ErrorCode.UNKNOWN_ENTITY.value,
    )


@mutator("type_corruption")
def _type_corruption(run: _Run, rng: random.Random) -> Mutation:
    f = _pick_file(run, rng, lambda f: bool(run.metric_fields(f, unambiguous=False)))
    k, metric, _ = rng.choice(
        [x for x in run.metric_fields(f, unambiguous=False) if x[1] not in run.mapping.enum_values]
    )
    hit = 0
    for r in f.records:
        if k in r and rng.random() < 0.2:
            r[k] = rng.choice(["N/A", "#ERR", "--", "null?"])
            hit += 1
    if not hit:
        raise NotApplicable("nothing corrupted")
    run.save(f)
    metrics = {a.metric for a in run.mapping.metric_aliases[normalise_key(k)]}
    return Mutation(
        "type_corruption",
        f.path.name,
        f"{hit} values of {k} replaced by junk",
        "unaffected",
        frozenset({ErrorCode.TYPE_MISMATCH}),
        affected_metrics=frozenset(metrics),
    )


@mutator("implausible_values")
def _implausible(run: _Run, rng: random.Random) -> Mutation:
    f = _pick_file(run, rng, lambda f: bool(run.metric_fields(f, unambiguous=False)))
    k, metric, _ = rng.choice(
        [x for x in run.metric_fields(f, unambiguous=False) if x[1] not in run.mapping.enum_values]
    )
    hit = 0
    for r in f.records:
        if k in r and rng.random() < 0.1 and _num(r[k]) is not None:
            r[k] = _fmt_like(r[k], -abs(_num(r[k]) or 1.0) - 1e6)
            hit += 1
    if not hit:
        raise NotApplicable("nothing changed")
    run.save(f)
    metrics = {a.metric for a in run.mapping.metric_aliases[normalise_key(k)]}
    return Mutation(
        "implausible_values",
        f.path.name,
        f"{hit} values of {k} made impossible",
        "unaffected",
        frozenset({ErrorCode.IMPLAUSIBLE_VALUE}),
        affected_metrics=frozenset(metrics),
    )


# ----------------------------------------------------------------------------- unrecoverable
@mutator("drop_timestamp_field")
def _drop_ts(run: _Run, rng: random.Random) -> Mutation:
    f = _pick_file(run, rng)
    k = run.ts_field(f)
    for r in f.records:
        r.pop(k, None)
    run.save(f)
    return Mutation(
        "drop_timestamp_field",
        f.path.name,
        f"{k} removed",
        "unaffected",
        frozenset({ErrorCode.MISSING_FIELD}),
        affected_entities=frozenset({"*" + f.path.name}),
    )


@mutator("drop_entity_field")
def _drop_entity(run: _Run, rng: random.Random) -> Mutation:
    f = _pick_file(run, rng)
    ids = run.id_fields(f)
    for r in f.records:
        for k in ids:
            r.pop(k, None)
    run.save(f)
    return Mutation(
        "drop_entity_field",
        f.path.name,
        f"{ids} removed",
        "unaffected",
        frozenset({ErrorCode.MISSING_FIELD}),
        affected_entities=frozenset({"*" + f.path.name}),
    )


@mutator("garble_lines")
def _garble(run: _Run, rng: random.Random) -> Mutation:
    f = _pick_file(run, rng)
    lines = f.path.read_text(encoding="utf-8").splitlines()
    n = max(1, len(lines) // 20)
    bad_rows = sorted(rng.sample(range(1, len(lines)), n))
    affected: set[str] = set()
    for i in bad_rows:
        if f.fmt == "csv":
            lines[i] = lines[i] + ",EXTRA,CELLS"
        else:
            lines[i] = lines[i][: len(lines[i]) // 2]
    if f.fmt != "csv":
        for i in bad_rows:
            # JSONL line i (0-based) holds record i
            if i < len(f.records):
                affected |= run.record_entities(f.records[i])
    f.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return Mutation(
        "garble_lines",
        f.path.name,
        f"{n} lines garbled",
        "unaffected",
        frozenset({ErrorCode.MALFORMED_INPUT}),
        affected_entities=frozenset(affected),
        ignore_time=False,
    )


@mutator("binary_junk")
def _binary(run: _Run, rng: random.Random) -> Mutation:
    f = _pick_file(run, rng)
    f.path.write_bytes(bytes(rng.randrange(128, 256) for _ in range(512)))
    return Mutation(
        "binary_junk",
        f.path.name,
        "file replaced by non-UTF-8 bytes",
        "unaffected",
        frozenset({ErrorCode.MALFORMED_INPUT}),
        affected_entities=frozenset({"*" + f.path.name}),
    )


@mutator("unknown_unit_field")
def _unknown_unit(run: _Run, rng: random.Random) -> Mutation:
    f = _pick_file(run, rng, lambda f: bool(run.metric_fields(f)))
    k, metric, _ = rng.choice(run.metric_fields(f))
    new = f"{k}_furlongs"
    _rename(f, k, new)
    run.save(f)
    return Mutation(
        "unknown_unit_field",
        f.path.name,
        f"{k} -> {new}",
        "unaffected",
        frozenset({ErrorCode.UNKNOWN_FIELD}),
        affected_metrics=frozenset({metric}),
    )


@mutator("missing_entity_values")
def _missing_entity_values(run: _Run, rng: random.Random) -> Mutation:
    f = _pick_file(run, rng)
    ids = run.id_fields(f)
    hit = 0
    affected: set[str] = set()
    for r in f.records:
        if rng.random() < 0.05:
            affected |= run.record_entities(r)
            for k in ids:
                r.pop(k, None)
            hit += 1
    if not hit:
        raise NotApplicable("nothing dropped")
    run.save(f)
    return Mutation(
        "missing_entity_values",
        f.path.name,
        f"entity id removed from {hit} records",
        "unaffected",
        frozenset({ErrorCode.MISSING_FIELD}),
        affected_entities=frozenset(affected),
    )


# ----------------------------------------------------------------------------- driver
def mutate(src: Path, dst: Path, kind: str, seed: int, mapping: Mapping | None = None) -> Mutation:
    """Copy run ``src`` to ``dst`` and apply mutation ``kind`` deterministically."""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    rng = random.Random(f"{kind}:{seed}:{src.name}")
    return MUTATORS[kind](_Run(dst, mapping or get_mapping()), rng)


# ----------------------------------------------------------------------------- checking
SeriesId = tuple[str, str, str | None]


def _series_map(result: Any) -> dict[SeriesId, Any]:
    return {(o.entity.entity_id, o.metric, o.observed_from): o for o in result.observations}


def _same_values(a: Any, b: Any, ignore_time: bool, tol: float) -> bool:
    if len(a.points) != len(b.points):
        return False
    for p, q in zip(a.points, b.points, strict=True):
        if not ignore_time and p.t != q.t:
            return False
        if isinstance(p.v, str) or isinstance(q.v, str):
            if p.v != q.v:
                return False
        elif abs(p.v - q.v) > tol * max(1.0, abs(p.v)):
            return False
    return True


def check(base: Any, mutated: Any, m: Mutation, tol: float = 1e-9) -> list[str]:
    """Return a list of failures (empty = the Translator handled the mutation correctly).

    ``base`` / ``mutated`` are TranslationResults of the original and mutated run.
    """
    failures = [
        f"expected error code {c.value} not reported"
        for c in sorted(m.expect_codes - mutated.error_codes())
    ]
    bm, mm = _series_map(base), _series_map(mutated)

    def rename(x: str | None) -> str | None:
        return m.renamed_entities.get(x, x) if x is not None else None

    for key, obs in bm.items():
        eid, metric, observed = key
        files = {s.source for s in obs.sources}
        affected = m.file in files and (
            eid in m.affected_entities
            or (observed in m.affected_entities)
            or metric in m.affected_metrics
            or any(f"*{f}" in m.affected_entities for f in files)
        )
        in_file = m.file in files
        target = mm.get((rename(eid) or eid, metric, rename(observed)) if in_file else key)
        if m.values == "flagged" and affected:
            if target is None:
                failures.append(f"{key}: ambiguous series missing instead of flagged")
            elif m.flag_issue and m.flag_issue not in target.quality.issues:
                failures.append(f"{key}: ambiguity not flagged in quality issues")
            continue
        if m.values == "unaffected" and affected:
            continue
        if target is None:
            failures.append(f"{key}: series lost")
            continue
        if not _same_values(obs, target, m.ignore_time, tol):
            failures.append(f"{key}: canonical values differ")
        renamed = in_file and (eid in m.renamed_entities or observed in m.renamed_entities)
        if (
            m.flag_issue
            and m.values == "all"
            and (affected or renamed)
            and m.flag_issue not in target.quality.issues
        ):
            failures.append(f"{key}: expected quality issue {m.flag_issue} missing")
    return failures


@dataclass
class CorpusRow:
    run: str
    dialect: str
    kind: str
    outcome: Literal["pass", "fail", "crash", "n/a"]
    detail: str
    failures: list[str] = field(default_factory=list)


def run_corpus(
    runs: list[Path], workdir: Path, translator: Any, kinds: list[str] | None = None
) -> list[CorpusRow]:
    """Apply every mutation kind to every run and check the Translator's handling."""
    rows: list[CorpusRow] = []
    for run in runs:
        base = translator.translate(run, "baseline")
        dialect = ",".join(sorted(set(base.dialects.values())))
        for i, kind in enumerate(kinds or list(MUTATORS)):
            dst = workdir / f"{run.name}__{kind}"
            try:
                m = mutate(run, dst, kind, seed=i)
            except NotApplicable as exc:
                rows.append(CorpusRow(run.name, dialect, kind, "n/a", str(exc)))
                continue
            try:
                result = translator.translate(dst, "mutated")
            except Exception as exc:  # noqa: BLE001 - a crash is exactly what we are measuring
                rows.append(
                    CorpusRow(run.name, dialect, kind, "crash", f"{type(exc).__name__}: {exc}")
                )
                continue
            finally:
                shutil.rmtree(dst, ignore_errors=True)
            fails = check(base, result, m)
            rows.append(
                CorpusRow(run.name, dialect, kind, "fail" if fails else "pass", m.detail, fails)
            )
    return rows


def select_runs(root: Path, per_family: int) -> list[Path]:
    """Evenly spaced runs from every family directory (deterministic, never hand-picked)."""
    out: list[Path] = []
    for fam in sorted(p for p in root.iterdir() if p.is_dir()):
        runs = sorted(p for p in fam.iterdir() if p.is_dir())
        if runs:
            step = len(runs) / per_family
            out += [runs[int(i * step + step / 2)] for i in range(min(per_family, len(runs)))]
    return out


def render_corpus(rows: list[CorpusRow]) -> str:
    kinds = list(dict.fromkeys(r.kind for r in rows))
    runs = sorted({r.run for r in rows})
    total = {o: sum(1 for r in rows if r.outcome == o) for o in ("pass", "fail", "crash", "n/a")}
    lines = [
        "# Interop robustness results",
        "",
        "Generated by `netcoop interop-eval`. Each generated run is mutated once per mutation kind",
        "(netcoop/mutation.py) and the Translator's output is checked against the unmutated run:",
        "recoverable mutations must reproduce identical canonical values, ambiguous ones must be",
        "flagged, and destructive ones must raise the expected typed error, without crashing.",
        "",
        f"**{len(rows)} cases over {len(runs)} runs: {total['pass']} pass, {total['fail']} fail, "
        f"{total['crash']} crash, {total['n/a']} not applicable.**",
        "",
        "| mutation | expectation | pass | fail | crash | n/a | example |",
        "|---|---|---|---|---|---|---|",
    ]
    for k in kinds:
        rs = [r for r in rows if r.kind == k]
        c = {o: sum(1 for r in rs if r.outcome == o) for o in ("pass", "fail", "crash", "n/a")}
        example = next((r.detail for r in rs if r.outcome != "n/a"), "")
        doc = (MUTATORS[k].__doc__ or "").strip()
        lines.append(
            f"| `{k}` | {_EXPECTATION.get(k, doc)} | {c['pass']} | {c['fail']} | {c['crash']} | "
            f"{c['n/a']} | {example.replace('|', '/')} |"
        )
    bad = [r for r in rows if r.outcome in ("fail", "crash")]
    lines += ["", "## Failures", ""]
    lines += [
        f"- `{r.kind}` on `{r.run}`: {r.detail}; {'; '.join(r.failures[:3])}" for r in bad
    ] or ["None."]
    lines += ["", "## Runs", "", *[f"- `{r}`" for r in runs], ""]
    return "\n".join(lines)


_EXPECTATION = {
    "rename_case": "recover exact values",
    "rename_alias": "recover exact values",
    "unit_change": "recover exact values",
    "timestamp_format": "recover exact values",
    "enum_case": "recover exact values",
    "schema_version_change": "recover + INCOMPATIBLE_SCHEMA warning",
    "unknown_extra_field": "recover + UNKNOWN_FIELD warning (field preserved)",
    "shuffle_records": "recover exact values",
    "duplicate_records": "recover + DUPLICATE_SAMPLE warning",
    "drop_topology": "recover + MISSING_TOPOLOGY warning",
    "drop_unit_suffix": "flag AMBIGUOUS_UNIT on affected series",
    "stale_entity": "keep values + STALE_DATA flag",
    "file_time_shift": "keep values + CLOCK_SKEW / STALE_DATA",
    "unknown_devices": "keep values + UNKNOWN_ENTITY flag",
    "type_corruption": "drop bad samples + TYPE_MISMATCH; others exact",
    "implausible_values": "drop bad samples + IMPLAUSIBLE_VALUE; others exact",
    "drop_timestamp_field": "file unusable: fatal MISSING_FIELD; others exact",
    "drop_entity_field": "file unusable: fatal MISSING_FIELD; others exact",
    "garble_lines": "skip bad lines + MALFORMED_INPUT; others exact",
    "binary_junk": "file unusable: fatal MALFORMED_INPUT; others exact",
    "unknown_unit_field": "field unused + UNKNOWN_FIELD; others exact",
    "missing_entity_values": "skip records + MISSING_FIELD; others exact",
}
