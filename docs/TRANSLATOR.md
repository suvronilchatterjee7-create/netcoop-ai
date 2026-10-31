# Translator / Normalization agent

The Translator is the system's only contact with raw telemetry. It turns files in any known
dialect into canonical protocol messages (`TOPOLOGY`, `OBSERVATION`, `ERROR`), so that no
other agent ever sees a source field name, a source unit or a schema version.

```bash
netcoop translate data/generated/interop_failure/<run> --out runs/x/observations.jsonl
netcoop interop-eval          # mutated-corpus robustness check -> docs/INTEROP_RESULTS.md
```

## Where the knowledge lives

| what | file | changed by |
|---|---|---|
| field aliases, entity bindings, enum values, topology field names, dialect profiles | `data/mappings/canonical.yaml` | adding a dialect |
| canonical metrics, units, conversion factors, physical ranges | `data/vocabulary/*.yaml` | adding a metric or unit |
| certainty levels, staleness/skew tolerances, quality weights, inference rule | `config/translator.yaml` | tuning (each value has a rationale and a source) |

The code contains no source field names, unit factors, device names or thresholds.
Supporting a new dialect means adding aliases to the mapping file.

## Pipeline

1. **Syntactic** (`readers.py`). Reads CSV, JSON and JSONL, sniffing the content when the
   extension is unknown. A file that is unreadable, empty or not UTF-8 is `MALFORMED_INPUT`
   (fatal for that file only). Bad JSONL lines and over-long CSV rows are skipped and recorded
   (recoverable).
2. **Classification.** A table is topology if it is a node or edge list in a JSON document,
   or a table with endpoint columns, no timestamp, and no metric fields other than capacity.
   Everything else is telemetry.
3. **Topology** (`topology.py`). Reads nodes, parent pointers and edges. Node-type values are
   normalised (`RTR` → `router`). Direction is inferred from parent pointers or from
   parent/child column pairs, and the root is the unique node with no upstream. Links without
   ids get `link_id_template` from the mapping file. Missing topology is a `MISSING_TOPOLOGY`
   warning, and the run continues.
4. **Structural**, per telemetry table:
   - Field names are normalised (`Latency-MS` → `latency_ms`).
   - The timestamp field is found; without one the table is unusable (fatal `MISSING_FIELD`).
   - Each record's entity is resolved with the first matching *binding*: link id, endpoint
     pair, AP id, device id, or service plus vantage point. Records with no identifier are
     skipped (recoverable `MISSING_FIELD`).
   - Unknown fields are reported once per table (`UNKNOWN_FIELD`), with example values kept
     in `TranslationResult.unknown_fields`. A "did you mean" suggestion is given when the
     field is close to a known alias, but it is **never applied**.
5. **Units**, per (field, entity category):
   - A unit declared by the alias wins.
   - Otherwise the unit is read from the field-name suffix (`_us`, `_pct`, `_kbps`, ...).
   - Otherwise it is inferred from plausibility: a proportion column whose values never
     exceed 1 is read as a ratio, anything else in that dimension as the canonical unit. This
     is flagged `AMBIGUOUS_UNIT` and certainty is reduced.
   - When an alias is shared by two metrics, the entity category decides: `loss_pct` on a link
     is `packet_loss`, on an AP it is `wireless_packet_loss`.
6. **Semantic.**
   - Values must be numeric or a valid enum value (`TYPE_MISMATCH` otherwise).
   - After conversion they must be inside the metric's physical range (`IMPLAUSIBLE_VALUE`
     otherwise). Bad samples are dropped and counted in plausibility.
   - A metric that does not apply to the entity type is `INAPPLICABLE_METRIC`.
7. **Temporal.**
   - Timestamps are parsed as ISO-8601 or as epoch seconds/milliseconds (split at a magnitude
     of 1e11) and converted to UTC. Naive timestamps are taken as UTC and flagged.
   - Samples are sorted, and duplicates at the same timestamp are dropped (`DUPLICATE_SAMPLE`).
   - The *reference time* is the median of each source's newest timestamp. A source more than
     `clock_skew_tolerance_intervals` from it is flagged `CLOCK_SKEW`. A series whose last
     sample is older than `stale_after_intervals` is flagged `STALE_DATA`, and its freshness
     decays with a half-life.
8. **Referential.** Entities and vantage points that are not in the topology are kept but
   flagged `UNKNOWN_ENTITY`, with reduced mapping certainty.
9. **Quality and output.**
   - Each series gets a `DataQuality` record: completeness, freshness, plausibility and
     mapping certainty, combined by a weighted geometric mean (SCORING.md §1), plus issue tags.
   - Every sample keeps its own `SourceRef` (file, line or row, original field name).
   - Record-level problems are aggregated into one typed `ERROR` per (code, file, field), with
     an occurrence count and the first location.

## Failure semantics

The Translator never raises on input data. Each problem gets one of three severities:

- **Fatal:** a file or table cannot be used. The rest of the input is still processed.
- **Recoverable:** something was dropped or repaired, and the repair is recorded.
- **Warning:** the data is usable but less trustworthy.

All errors are posted as `ERROR` messages and later go into the report's `limitations`.
Quality scores carry the remaining doubt forward to the correlator.

## Verification: the mutated corpus

`netcoop/mutation.py` takes valid generated runs and applies 22 kinds of systematic
corruption: field renames, alias swaps, unit changes, timestamp formats, enum case, schema
version, unknown fields, shuffling, duplicates, dropped topology, removed units, stale
entities, shifted files, unknown devices, type corruption, impossible values, dropped
timestamp or entity fields, garbled lines, binary junk, unknown units and missing entity
values. Each mutation declares what the Translator must do:

- **exact recovery:** every canonical series is identical to the unmutated run
- **flagged ambiguity:** the affected series carry the issue in their quality record
- **typed error:** the expected `ErrorCode`, with untouched data still exact

`netcoop interop-eval` runs every mutation on runs picked evenly from every scenario family
and writes [INTEROP_RESULTS.md](INTEROP_RESULTS.md). The test suite runs the same check on
freshly generated native and legacy runs and requires every mutation kind to be exercised.

## Known limitations

- **Plausibility inference** can misread a percentage column that never exceeds 1%, and has
  no way to tell µs from ms in a unit-less time column. Both cases are flagged
  (`AMBIGUOUS_UNIT`, certainty 0.7); they are not silently "fixed".
- **Staleness is relative** to the newest data in the input. A run where every source is
  equally old cannot be detected as stale without an external "now" (a future
  `--analysis-time` option).
- **Unrecognised dialects** are detected only for reporting. Mapping is alias-based, so an
  unrecognised dialect still works as long as its field names are covered by aliases.
