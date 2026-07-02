# ADR 0024: Domain technology stack & portability (§24.21)

- **Status:** accepted
- **Date:** 2026-07-03

## Decision

**Primary stack (implemented):** Kuzu (embedded Cypher) / Neo4j (server) property
graph; Qdrant + BM25 search; GLiNER/LLM + rule extraction; LangGraph agent; OSS
LLMs (Qwen2.5/DeepSeek-V3/Mistral). This closes all functional requirements.

**Alternatives evaluated, not implemented** (reference/benchmark, see
`third_party/CATALOG.md`):

| Concern | Alternatives | Status | Note |
|---|---|---|---|
| Graph portability | Amazon Neptune, JanusGraph | reference | Cypher/GDS/APOC-specific parts (fulltext/vector index DDL, `apoc.*`, `gds.*`) block a drop-in move; Gremlin mapping of the 6 domain templates is documented as a spike. |
| Keyword search | Elasticsearch, Vespa | benchmark | OpenSearch mapping parity; Vespa adds native hybrid ranking. Not required. |
| RU NLP | DeepPavlov, spaCy-ru, ruBERT/SlavicBERT | benchmark | Optional `Extractor`-protocol backends, disabled by default; current GLiNER/LLM + declension-tolerant matcher covers RU/EN. |

## OWL/RDF boundary

The **operational** store is a property graph. OWL/RDF/SHACL/JSON-LD are the
**interoperability/export** layer only (`resources/shapes.ttl`,
`docs/domain/fair_and_standards.md`) — no SPARQL-first stack.

## Consequence

The primary stack delivers all requirements; every recommended alternative is
evaluated and catalogued, so switching later is a scoped migration, not a rewrite.
