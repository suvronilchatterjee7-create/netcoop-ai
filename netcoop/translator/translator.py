"""Translator / Normalization agent: raw telemetry in any known dialect -> canonical messages.

Layers (docs/TRANSLATOR.md):

1. syntactic   - files parse (readers.py)
2. structural  - timestamp and entity identifier present; known vs unknown fields
3. semantic    - values numeric / valid enum, physically plausible after unit conversion
4. temporal    - ordering, duplicates, staleness and clock skew per source
5. referential - entities exist in the topology

The Translator never raises on bad input: every problem becomes an aggregated, typed
ERROR, recoverable problems are repaired and recorded, and quality scores carry the
remaining doubt forward to the correlator.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from netcoop.config import get_value, load_config
from netcoop.generation import LABEL_FILES
from netcoop.protocol.capability import AgentRole, CapabilityCard
from netcoop.protocol.common import (
    PROTOCOL_VERSION,
    EntityRef,
    ErrorCode,
    MessageType,
    Severity,
    SourceRef,
)
from netcoop.protocol.messages import Envelope, make_message
from netcoop.protocol.payloads import ErrorPayload, ObservationPayload, Point, TopologyPayload
from netcoop.protocol.vocabulary import Vocabulary, get_vocabulary
from netcoop.translator.issues import IssueLog
from netcoop.translator.mapping import Binding, Mapping, UnitInfo, get_mapping, normalise_key
from netcoop.translator.quality import combine, freshness
from netcoop.translator.readers import RawTable, parse_timestamp, read_path
from netcoop.translator.topology import Graph, build_graph, is_topology_table, topology_payload

AGENT_ID = "translator"
INPUT = "input"  # pseudo-source for input-wide issues

SeriesKey = tuple[str, str, str, str | None]  # entity_id, entity_type, metric, observed_from


@dataclass
class _Series:
    points: list[tuple[datetime, float | str, SourceRef]] = field(default_factory=list)
    rejected: int = 0
    certainty: float = 1.0
    issues: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)


@dataclass
class _Column:
    """How one (normalised field, entity category) column maps to the vocabulary."""

    metric: str
    unit: UnitInfo | None
    certainty: float
    inferred: bool = False


@dataclass
class TranslationResult:
    incident_id: str
    topology: TopologyPayload | None
    observations: list[ObservationPayload]
    errors: list[ErrorPayload]
    messages: list[Envelope]
    dialects: dict[str, str]
    unknown_fields: dict[str, dict[str, list[str]]]
    entity_quality: dict[str, float]
    reference_time: datetime | None
    stats: dict[str, int]

    def series(
        self, entity_id: str, metric: str, observed_from: str | None = None
    ) -> ObservationPayload | None:
        for o in self.observations:
            if (
                o.entity.entity_id == entity_id
                and o.metric == metric
                and o.observed_from == observed_from
            ):
                return o
        return None

    def error_codes(self) -> set[ErrorCode]:
        return {e.code for e in self.errors}


def capability_card() -> CapabilityCard:
    return CapabilityCard(
        agent_id=AGENT_ID,
        version="0.1.0",
        role=AgentRole.TRANSLATOR,
        description="Validates raw telemetry, maps fields/units/versions to the vocabulary, "
        "scores data quality and emits TOPOLOGY, OBSERVATION and ERROR messages.",
        protocol_versions=("1.0", PROTOCOL_VERSION),
        consumes_types=(),
        produces_types=(MessageType.TOPOLOGY, MessageType.OBSERVATION, MessageType.ERROR),
    )


class Translator:
    def __init__(self, mapping: Mapping | None = None, vocab: Vocabulary | None = None) -> None:
        self.mapping = mapping or get_mapping()
        self.vocab = vocab or get_vocabulary()
        cfg = load_config("translator")
        self.cfg = cfg
        self.c_exact = float(get_value(cfg, "mapping_certainty.exact"))
        self.c_norm = float(get_value(cfg, "mapping_certainty.normalised"))
        self.c_suffix = float(get_value(cfg, "mapping_certainty.unit_from_suffix"))
        self.c_inferred = float(get_value(cfg, "mapping_certainty.unit_inferred"))
        self.c_unresolved = float(get_value(cfg, "mapping_certainty.entity_unresolved"))
        self.epoch_ms = float(get_value(cfg, "time.epoch_ms_threshold"))
        self.ratio_max = float(get_value(cfg, "units.ratio_if_column_max_at_most"))
        self.fuzzy_cutoff = float(get_value(cfg, "reporting.fuzzy_suggestion_cutoff"))
        self.max_examples = int(get_value(cfg, "reporting.max_unknown_value_examples"))
        self.stale_intervals = float(get_value(cfg, "time.stale_after_intervals"))
        self.skew_intervals = float(get_value(cfg, "time.clock_skew_tolerance_intervals"))
        self.metric_dim = {
            m: next(d for d, dim in self.vocab.dimensions.items() if dim.canonical == mdef.unit)
            for m, mdef in self.vocab.metrics.items()
        }

    # ------------------------------------------------------------------ public
    def translate(self, inputs: Path | list[Path], incident_id: str) -> TranslationResult:
        log = IssueLog()
        files = self._files(inputs, log)
        tables: list[RawTable] = []
        for f in files:
            tables += read_path(f, log)

        dialects: dict[str, str] = {}
        by_source: dict[str, set[str]] = defaultdict(set)
        for t in tables:
            for _, r in t.records:
                by_source[t.source] |= {normalise_key(k) for k in r}
        for src, keys in by_source.items():
            dialects[src] = self.mapping.detect_dialect(keys)

        topo_tables = [t for t in tables if is_topology_table(t, self.mapping)]
        data_tables = [t for t in tables if t not in topo_tables]
        graph = build_graph(topo_tables, self.mapping, log)
        if not graph.present:
            log.add(
                ErrorCode.MISSING_TOPOLOGY,
                Severity.WARNING,
                INPUT,
                "no topology found; entities cannot be placed and localisation will degrade",
            )

        series: dict[SeriesKey, _Series] = defaultdict(_Series)
        grids: dict[str, set[datetime]] = defaultdict(set)
        unknown: dict[str, dict[str, list[str]]] = defaultdict(dict)
        for t in data_tables:
            self._process_table(
                t, graph, dialects.get(t.source, "unrecognised"), series, grids, unknown, log
            )

        reference, interval = self._clock(grids, log)
        observations = self._build_observations(series, grids, reference, interval, log)
        topology = topology_payload(graph, dialects) if graph.present else None
        errors = log.to_payloads(dialects)

        entity_q: dict[str, list[float]] = defaultdict(list)
        for o in observations:
            entity_q[o.entity.entity_id].append(o.quality.score)
        msg_time = reference or datetime(1970, 1, 1, tzinfo=UTC)
        messages: list[Envelope] = []
        if topology is not None:
            messages.append(self._msg(MessageType.TOPOLOGY, topology, incident_id, msg_time))
        messages += [
            self._msg(MessageType.OBSERVATION, o, incident_id, msg_time) for o in observations
        ]
        messages += [self._msg(MessageType.ERROR, e, incident_id, msg_time) for e in errors]
        return TranslationResult(
            incident_id=incident_id,
            topology=topology,
            observations=observations,
            errors=errors,
            messages=messages,
            dialects=dialects,
            unknown_fields={k: dict(v) for k, v in unknown.items()},
            entity_quality={k: statistics.fmean(v) for k, v in sorted(entity_q.items())},
            reference_time=reference,
            stats={
                "files": len(files),
                "tables": len(tables),
                "topology_tables": len(topo_tables),
                "series": len(observations),
                "samples": sum(len(o.points) for o in observations),
                "errors": len(errors),
            },
        )

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _msg(t: MessageType, payload: Any, incident: str, ts: datetime) -> Envelope:
        return make_message(
            t, sender=AGENT_ID, correlation_id=incident, payload=payload, timestamp=ts
        )

    @staticmethod
    def _files(inputs: Path | list[Path], log: IssueLog) -> list[Path]:
        paths = [inputs] if isinstance(inputs, Path) else list(inputs)
        files: list[Path] = []
        for p in paths:
            if p.is_dir():
                files += sorted(f for f in p.iterdir() if f.is_file() and f.name not in LABEL_FILES)
            elif p.is_file():
                files.append(p)
            else:
                log.add(
                    ErrorCode.MALFORMED_INPUT, Severity.FATAL, p.name, "input path does not exist"
                )
        if not files:
            log.add(ErrorCode.MALFORMED_INPUT, Severity.FATAL, INPUT, "no input files")
        return files

    def _binding_for(self, rec: dict[str, Any]) -> Binding | None:
        for b in self.mapping.bindings:
            if any(rec.get(f) not in (None, "") for f in b.id_fields):
                return b
            if any(
                rec.get(a) not in (None, "") and rec.get(z) not in (None, "")
                for a, z in b.endpoint_fields
            ):
                return b
        return None

    def _resolve_entity(
        self, b: Binding, rec: dict[str, Any], graph: Graph, source: str, loc: str, log: IssueLog
    ) -> tuple[EntityRef, str | None, bool]:
        """Returns (entity, observed_from, resolved_in_topology)."""
        resolved = True
        if b.endpoint_fields:
            a, z = next(
                (str(rec[x]), str(rec[y]))
                for x, y in b.endpoint_fields
                if rec.get(x) not in (None, "") and rec.get(y) not in (None, "")
            )
            link = graph.link_between(a, z)
            if link is None:
                link = str(self.mapping.topology["link_id_template"]).format(a=a, b=z)
                resolved = not graph.present
            entity = EntityRef(entity_id=link, entity_type=b.entity_type)
        else:
            raw = next(str(rec[f]) for f in b.id_fields if rec.get(f) not in (None, ""))
            eid = raw.lower() if b.value_case == "lower" else raw
            if b.entity_type == "from_topology":
                etype = graph.entity_type(eid)
                resolved = etype is not None or not graph.present
                entity = EntityRef(entity_id=eid, entity_type=etype or "device")
            else:
                entity = EntityRef(entity_id=eid, entity_type=b.entity_type)
                if graph.present and b.entity_type == "link":
                    resolved = eid in graph.edges
                elif graph.present and self.vocab.category_of(b.entity_type) == "device":
                    resolved = eid in graph.node_types
        observed = next(
            (str(rec[f]) for f in b.observed_from_fields if rec.get(f) not in (None, "")), None
        )
        if observed is not None and graph.present and observed not in graph.node_types:
            resolved = False
        if not resolved:
            log.add(
                ErrorCode.UNKNOWN_ENTITY,
                Severity.RECOVERABLE,
                source,
                "entity not present in topology; data kept with reduced certainty",
                locator=loc,
                entity_id=observed
                if observed and observed not in graph.node_types
                else entity.entity_id,
            )
        return entity, observed, resolved

    def _column(
        self, key: str, original: str, category: str, values: list[Any], source: str, log: IssueLog
    ) -> _Column | None:
        alias = self.mapping.metric_for(key, category)
        if alias is None:
            return None
        metric = alias.metric
        dim = self.metric_dim[metric]
        exact = original == key
        if alias.unit is not None:
            info = self.mapping.unit(alias.unit)
            return _Column(metric, info, self.c_exact if exact else self.c_norm)
        info = self.mapping.unit_from_suffix(key, dim)
        if info is not None:
            return _Column(metric, info, self.c_suffix if exact else self.c_suffix * self.c_norm)
        canonical = self.vocab.dimensions[dim].canonical
        if self.vocab.metrics[metric].kind == "enum" or len(self.vocab.dimensions[dim].units) == 1:
            return _Column(
                metric, self.mapping.unit(canonical), self.c_exact if exact else self.c_norm
            )
        nums = [v for v in (_to_float(x) for x in values) if v is not None]
        chosen = canonical
        if dim == "proportion" and nums and max(nums) <= self.ratio_max:
            chosen = "ratio"
        log.add(
            ErrorCode.AMBIGUOUS_UNIT,
            Severity.WARNING,
            source,
            f"no unit for field; inferred {chosen!r} from value plausibility",
            field=original,
            metric=metric,
            inferred_unit=chosen,
        )
        return _Column(metric, self.mapping.unit(chosen), self.c_inferred, inferred=True)

    def _process_table(
        self,
        table: RawTable,
        graph: Graph,
        dialect: str,
        series: dict[SeriesKey, _Series],
        grids: dict[str, set[datetime]],
        unknown: dict[str, dict[str, list[str]]],
        log: IssueLog,
    ) -> None:
        src = table.source
        originals: dict[str, str] = {}
        for _, r in table.records:
            for k in r:
                originals.setdefault(normalise_key(k), k)
        keys = set(originals)
        ts_key = next((k for k in originals if k in self.mapping.timestamp_fields), None)
        if ts_key is None:
            log.add(
                ErrorCode.MISSING_FIELD,
                Severity.FATAL,
                src,
                "no timestamp field; table cannot be used",
                expected=", ".join(sorted(self.mapping.timestamp_fields)),
            )
            return
        sv_key = next((k for k in originals if k in self.mapping.schema_version_fields), None)
        if sv_key:
            self._check_versions(table, sv_key, dialect, log)

        # Unknown fields: reported once per table, with examples, and preserved in the result.
        for k in sorted(keys):
            if not self.mapping.is_known(k):
                examples = list(
                    dict.fromkeys(
                        str(r.get(originals[k]))
                        for _, r in table.records
                        if r.get(originals[k]) is not None
                    )
                )[: self.max_examples]
                unknown.setdefault(src, {})[originals[k]] = examples
                suggestion = self.mapping.suggest(k, self.fuzzy_cutoff)
                extra = {"suggestion": suggestion} if suggestion else {}
                log.add(
                    ErrorCode.UNKNOWN_FIELD,
                    Severity.WARNING,
                    src,
                    "unknown field preserved but not used"
                    + (f"; did you mean {suggestion!r}?" if suggestion else ""),
                    field=originals[k],
                    **extra,
                )

        columns: dict[tuple[str, str], _Column | None] = {}
        any_binding = False
        for loc, raw in table.records:
            rec = {normalise_key(k): v for k, v in raw.items()}
            b = self._binding_for(rec)
            if b is None:
                log.add(
                    ErrorCode.MISSING_FIELD,
                    Severity.RECOVERABLE,
                    src,
                    "record has no entity identifier; skipped",
                    locator=loc,
                )
                continue
            any_binding = True
            if rec.get(ts_key) in (None, ""):
                log.add(
                    ErrorCode.MISSING_FIELD,
                    Severity.RECOVERABLE,
                    src,
                    "record has no timestamp; skipped",
                    field=originals[ts_key],
                    locator=loc,
                )
                continue
            ts = parse_timestamp(rec[ts_key], self.epoch_ms)
            if ts is None:
                log.add(
                    ErrorCode.MALFORMED_INPUT,
                    Severity.RECOVERABLE,
                    src,
                    "unparseable timestamp; record skipped",
                    field=originals[ts_key],
                    locator=loc,
                )
                continue
            if isinstance(rec[ts_key], str) and _is_naive_iso(rec[ts_key]):
                log.add(
                    ErrorCode.CLOCK_SKEW,
                    Severity.WARNING,
                    src,
                    "timestamp has no timezone; assumed UTC",
                    field=originals[ts_key],
                    locator=loc,
                )
            grids[src].add(ts)
            entity, observed, resolved = self._resolve_entity(b, rec, graph, src, loc, log)
            category = self.vocab.category_of(entity.entity_type)
            used = (
                set(b.id_fields)
                | set(b.observed_from_fields)
                | {x for p in b.endpoint_fields for x in p}
            )
            for k, v in rec.items():
                if k in used or k in (ts_key, sv_key) or v in (None, ""):
                    continue
                ck = (k, category)
                if ck not in columns:
                    col_values = [r.get(originals[k]) for _, r in table.records]
                    columns[ck] = self._column(k, originals[k], category, col_values, src, log)
                col = columns[ck]
                if col is None:
                    continue
                if not self.vocab.metric_applies(col.metric, entity.entity_type):
                    log.add(
                        ErrorCode.INAPPLICABLE_METRIC,
                        Severity.WARNING,
                        src,
                        f"metric {col.metric} does not apply to {entity.entity_type}; dropped",
                        field=originals[k],
                    )
                    continue
                s = series[(entity.entity_id, entity.entity_type, col.metric, observed)]
                s.sources.add(src)
                s.certainty = min(
                    s.certainty, col.certainty, 1.0 if resolved else self.c_unresolved
                )
                if col.inferred:
                    s.issues.add(ErrorCode.AMBIGUOUS_UNIT.value)
                if not resolved:
                    s.issues.add(ErrorCode.UNKNOWN_ENTITY.value)
                value = self._value(col, v, src, originals[k], loc, log)
                if value is None:
                    s.rejected += 1
                    continue
                s.points.append(
                    (
                        ts,
                        value,
                        SourceRef(source=src, dialect=dialect, locator=loc, raw_field=originals[k]),
                    )
                )
        if not any_binding and table.records:
            log.add(
                ErrorCode.MISSING_FIELD,
                Severity.FATAL,
                src,
                "no entity identifier field in any record; table cannot be used",
            )

    def _value(
        self, col: _Column, raw: Any, src: str, fld: str, loc: str, log: IssueLog
    ) -> float | str | None:
        mdef = self.vocab.metrics[col.metric]
        if mdef.kind == "enum":
            mapped = self.mapping.enum_values.get(col.metric, {}).get(str(raw).strip().lower())
            if mapped is None or mapped not in mdef.values:
                log.add(
                    ErrorCode.TYPE_MISMATCH,
                    Severity.RECOVERABLE,
                    src,
                    f"invalid {col.metric} value; sample dropped",
                    field=fld,
                    locator=loc,
                    example=str(raw),
                )
                return None
            return mapped
        num = _to_float(raw)
        if num is None:
            log.add(
                ErrorCode.TYPE_MISMATCH,
                Severity.RECOVERABLE,
                src,
                "non-numeric value; sample dropped",
                field=fld,
                locator=loc,
                example=str(raw)[:40],
            )
            return None
        value = num * (col.unit.factor if col.unit else 1.0)
        if not mdef.in_range(value):
            log.add(
                ErrorCode.IMPLAUSIBLE_VALUE,
                Severity.RECOVERABLE,
                src,
                f"value outside physical range {list(mdef.range or ())}; sample dropped",
                field=fld,
                locator=loc,
                example=value,
            )
            return None
        return value

    def _check_versions(self, table: RawTable, sv_key: str, dialect: str, log: IssueLog) -> None:
        seen = {
            str(v) for _, r in table.records for k, v in r.items() if normalise_key(k) == sv_key
        }
        known = {
            str(x)
            for x in self.mapping.dialect_profiles.get(dialect, {}).get("schema_versions", [])
        }
        for v in sorted(seen - known):
            log.add(
                ErrorCode.INCOMPATIBLE_SCHEMA,
                Severity.WARNING,
                table.source,
                f"unrecognised schema version {v!r} for dialect {dialect}; mapped by field aliases",
                field=sv_key,
                version=v,
            )

    def _clock(
        self, grids: dict[str, set[datetime]], log: IssueLog
    ) -> tuple[datetime | None, float | None]:
        """Reference time = median of per-source newest timestamps; flags skewed sources."""
        if not grids:
            return None, None
        newest = {s: max(g) for s, g in grids.items() if g}
        all_ts = sorted(set().union(*grids.values()))
        diffs = [(b - a).total_seconds() for a, b in zip(all_ts, all_ts[1:], strict=False) if b > a]
        per_source = [
            statistics.median(
                [(b - a).total_seconds() for a, b in zip(sorted(g), sorted(g)[1:], strict=False)]
            )
            for g in grids.values()
            if len(g) > 1
        ]
        interval = (
            statistics.median(per_source)
            if per_source
            else (statistics.median(diffs) if diffs else None)
        )
        ref_epoch = statistics.median_low(sorted(t.timestamp() for t in newest.values()))
        reference = datetime.fromtimestamp(ref_epoch, tz=UTC)
        if interval:
            for s, t in sorted(newest.items()):
                lag = (reference - t).total_seconds()
                if abs(lag) > self.skew_intervals * interval:
                    log.add(
                        ErrorCode.CLOCK_SKEW,
                        Severity.WARNING,
                        s,
                        f"source time range is {'behind' if lag > 0 else 'ahead of'} the input "
                        f"by {abs(lag):.0f} s",
                        lag_s=lag,
                    )
        return reference, interval

    def _build_observations(
        self,
        series: dict[SeriesKey, _Series],
        grids: dict[str, set[datetime]],
        reference: datetime | None,
        interval: float | None,
        log: IssueLog,
    ) -> list[ObservationPayload]:
        out: list[ObservationPayload] = []
        for key in sorted(series, key=lambda k: (k[0], k[2], k[3] or "")):
            s = series[key]
            entity_id, entity_type, metric, observed = key
            if not s.points:
                continue
            pts = sorted(s.points, key=lambda p: p[0])
            dedup: list[tuple[datetime, float | str, SourceRef]] = []
            for p in pts:
                if dedup and dedup[-1][0] == p[0]:
                    log.add(
                        ErrorCode.DUPLICATE_SAMPLE,
                        Severity.WARNING,
                        p[2].source,
                        "duplicate timestamp for one series; first sample kept",
                        field=p[2].raw_field,
                    )
                    continue
                dedup.append(p)
            grid = set().union(*(grids[src] for src in s.sources))
            completeness = min(1.0, len(dedup) / len(grid)) if grid else 0.0
            plausibility = len(dedup) / (len(dedup) + s.rejected)
            fresh = 1.0
            issues = set(s.issues)
            if reference is not None and interval:
                age = abs((reference - dedup[-1][0]).total_seconds())
                fresh = freshness(age, interval)
                if age > self.stale_intervals * interval:
                    issues.add(ErrorCode.STALE_DATA.value)
                    log.add(
                        ErrorCode.STALE_DATA,
                        Severity.WARNING,
                        dedup[-1][2].source,
                        "series is stale relative to the rest of the input",
                        field=dedup[-1][2].raw_field,
                    )
            if s.rejected:
                issues.add("samples_rejected")
            sources = tuple(p[2] for p in dedup)
            out.append(
                ObservationPayload(
                    entity=EntityRef(entity_id=entity_id, entity_type=entity_type),
                    metric=metric,
                    unit=self.vocab.metrics[metric].unit,
                    observed_from=observed,
                    points=tuple(Point(t=t, v=v, src=i) for i, (t, v, _) in enumerate(dedup)),
                    sources=sources,
                    quality=combine(completeness, fresh, plausibility, s.certainty, tuple(issues)),
                )
            )
        return out


def _to_float(x: Any) -> float | None:
    if isinstance(x, bool) or x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def _is_naive_iso(s: str) -> bool:
    s = s.strip()
    if not s or s.replace(".", "", 1).lstrip("-").isdigit():
        return False
    return not (s.endswith("Z") or "+" in s[10:] or "-" in s[10:])
