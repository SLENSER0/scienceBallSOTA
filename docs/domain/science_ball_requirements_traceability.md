# Requirements traceability — «Научный клубок»

Maps the problem statement (`docs/zadacha.md`) to the implementation and its test/demo.

| Requirement | Plan § | Service / package | Verification |
|---|---|---|---|
| Import & normalize RU/EN docs (PDF/DOCX/PPTX/XLSX, patents, reports) | §5, §24.5 | ingestion-service | `test_ingestion.py`; `make ingest` |
| NLP extraction of entities/relations/numeric constraints | §6, §24.6 | kg_extractors (rule + LLM) | `test_units.py`, `test_query_parser.py`, `test_ingestion.py` |
| Synonyms RU↔EN (электроэкстракция/electrowinning, ПВП/…) | §24.3 | kg_schema/taxonomy | `test_taxonomy.py` |
| Knowledge graph + ontology (Material/Process/Equipment/…) | §3, §24.2 | kg_schema, kg_retrievers (Kuzu) | `test_schema.py`, `test_graph_store.py` |
| Cypher-like traversal (3–4 levels) | §3.16, §12 | kg_retrievers.graph_retriever | `test_graph_retriever.py` |
| Semantic + numeric-range + multi-level filtering | §12, §24.4 | query_parser + graph_retriever | eval numeric/geo/time checks |
| Domestic vs foreign practice | §24.8 | query_parser (practice_type) | eval `practice` checks |
| Verification model (source, confidence, actualization) | §24.7 | dto + synthesize (confidence) | `AnswerPayload.confidence`, citations |
| Graph visualization + gaps/contradictions highlighting | §17, §24.10 | frontend GraphView | build; semantic encodings |
| Literature-review synthesis (consensus/disagreement) | §24.11 | agent-service.synthesize | LLM answer (verified live) |
| Gap detection ("no experiments for …") | §15, §25 | seed Gap + retriever | eval `cold_heap_leaching_gap` |
| Contradiction detection | §15 | seed Contradiction + retriever | eval `nickel_catholyte` |
| Access control (roles, restricted evidence) | §19, §24.14 | agent-service.access | `test_rbac_external_partner` |
| Export PDF/Markdown/JSON-LD | §24.16, §24.19 | api export router | `test_export_markdown` |
| Manager dashboards / coverage | §24.15 | api /admin/coverage + FE | `test_coverage` |
| Multilingual (RU/EN) | §24 | throughout | eval `ru_en_parity` |

## Problem-statement scenarios covered
- Loss of institutional memory → single evidence-first graph over the corpus.
- Duplicated literature reviews → synthesized cited reviews with source counts.
- Cross-disciplinary search → taxonomy + graph traversal linking water↔process↔metal.
- Slow decisions → NL query → answer in seconds (embedded).
- Contradictory conclusions → CONTRADICTS edges + disagreement display, not averaging.

## The four acceptance queries
Each has a formal case in `packages/kg_eval/data/domain_science_ball/cases.json`
with expected entities, numeric constraints, filters and evidence requirements;
all pass (`docs/eval/domain_science_ball_report.md`).
