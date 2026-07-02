# ADR 0003: Core technology stack

- **Status:** accepted
- **Date:** 2026-07-02

## Decision

| Concern | Target (server) | Embedded default | Rejected alternatives |
|---|---|---|---|
| Graph DB | Neo4j (+APOC/GDS) | Kuzu | ArangoDB, Memgraph, TypeDB, Neptune, JanusGraph |
| Vector | Qdrant | qdrant-client local | Weaviate, Milvus, pgvector |
| Keyword | OpenSearch | BM25 (rank-bm25) | Elasticsearch, Vespa |
| Ontology | LinkML + Pydantic | same | OWL/RDF-first (kept as export layer only) |
| Extraction | GLiNER + LLM + rules | rules + OSS LLM | pure-LLM, pure-rules |
| Units | pint | pint | custom |
| Entity resolution | Splink | rapidfuzz + rules | Dedupe, OpenRefine |
| Orchestration | Dagster | in-process pipeline | Airflow, Prefect |
| Agent | LangGraph | LangGraph | bare function-calling |
| Graph UI | Reagraph | Reagraph | Cytoscape, Sigma, G6, React-Flow |
| API | FastAPI | FastAPI | Flask, Litestar |
| Frontend | React + Vite + Tailwind | same | Next.js, SvelteKit |

All choices are OSS-licensed (Apache-2.0 / MIT / BSD / GPLv3 for Neo4j
Community). Rationale and per-concern trade-offs are captured in the task plan
(§4.1, §21) and ADR-0005 (embedded profile), ADR-0006 (OSS LLMs).
