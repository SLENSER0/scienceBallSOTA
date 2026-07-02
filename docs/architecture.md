# Architecture

## Monorepo (§6.1)

```
apps/
  api-gateway/        FastAPI public API (:8000) — query/graph/search/evidence/export/admin
  agent-service/      LangGraph agent (:8010) — plan → retrieve → synthesize
  ingestion-service/  parse (PDF/DOCX/PPTX/XLSX) → chunk → extract → upsert (:8020)
  graph-service/      Kuzu/Neo4j graph store: schema, migrations, upsert, Cypher templates
  search-service/     Qdrant(local) vector + BM25 keyword indexing/search
  extraction-service/ rules + LLM + unit-normalization + entity-resolution orchestration
  curation-service/   curation workflow, decision history, review queue, expert edits
  frontend/           React + Vite + Tailwind + Reagraph UI (:3000)
packages/
  kg_common/     config, DTOs (frontend contract), deterministic IDs, logging, telemetry
  kg_schema/     ontology: LinkML + Pydantic, labels, relationships, enums, extraction models
  kg_extractors/ rule/LLM/materials extractors, units, entity resolution
  kg_retrievers/ graph/vector/keyword/hybrid retrievers + GraphRAG
  kg_eval/       golden datasets, metrics, eval runner
infra/           docker-compose.yml, neo4j/, qdrant/, opensearch/, dagster/, helm/
docs/            adr/, conventions/, domain/, eval/ + task plan & guides
third_party/     vendored OSS reference repos (study only, git-ignored)
```

## Data flow

```
documents (data/)
   │  ingestion-service: DocumentParser → chunks (+ tables)
   ▼
extraction-service: rule extractors (units, ions, RU/EN synonyms)
                  + LLM extractor (OSS model) → EntityExtract / MeasurementExtract /
                    RelationExtract / ClaimExtract / NumericConstraintExtract
   │  normalization (pint) → entity resolution (rapidfuzz + vocab) → deterministic IDs
   ▼
graph-service (Kuzu): evidence-first upsert (MERGE), provenance, versioning
search-service: vector (fastembed→Qdrant local) + BM25 index over chunks & entities
   │
   ▼
kg_retrievers: structured graph templates + hybrid (vector⊕keyword) fusion + GraphRAG
   ▼
agent-service (LangGraph): parse query → numeric/geo/time filters → retrieve →
                           assemble evidence → synthesize (with citations, gaps,
                           contradictions, confidence)
   ▼
api-gateway (FastAPI) → frontend (chat, graph, tables, dashboards, evidence inspector)
```

## Ports (§13.1)

frontend 3000 · api 8000 · agent 8010 · ingestion 8020 · docling 5001 ·
neo4j 7474/7687 · qdrant 6333/6334 · opensearch 9200 · postgres 5432 ·
redis 6379 · minio 9000/9001 · dagster 3001.

## Source of truth

- Ontology: `packages/kg_schema` (labels/relationships/enums). `/api/v1/graph/schema`
  and the frontend TS types derive from it.
- Runtime profiles: ADR-0005. Stack: ADR-0003. OSS/licensing: ADR-0006.
- Full task plan: `docs/FULL_SYSTEM_TASKS_science_ball.md`.
