# Rubric traceability

| Criterion (weight) | Phases | Evidence for judges | Status |
|---|---|---|---|
| Interoperability and protocol (30%) | 1, 2, 3 | PROTOCOL.md, JSON Schemas, capability cards, version adapters, mutated-corpus recovery, REQUEST/RESPONSE traces | Phase 1 done: PROTOCOL.md, PROTOCOL_REFERENCE.md, docs/schemas, cards, 1.0<->2.0 adapters. Phase 2 done: TRANSLATOR.md, mapping file, INTEROP_RESULTS.md (mutated corpus) |
| Diagnostic accuracy and evidence (25%) | 4, 5, 7, 8 | EVALUATION.md metrics, provenance-linked evidence, localisation results | not started |
| Orchestration and conflict resolution (15%) | 3, 5, 6 | multi-round traces, failure isolation, courtroom transcripts, ablations | Phase 3 done: board, rounds, routing, isolation, deterministic trace + replay (ORCHESTRATION.md) |
| Robustness (15%) | 2, 5, 8 | robustness curves, typed errors, abstention precision | Phase 2: typed errors, data-quality scores, mutated corpus 0 fail / 0 crash |
| Innovation and extensibility (10%) | 6, 9 | courtroom, plugin/catalogue extensibility, MCP | not started |
| Code, docs and demo (5%) | 0, 8, 10 | CI, coverage, README, demo script | Phase 0 scaffold done |
