# ADR 0005: Embedded runtime profile (Kuzu / qdrant-local / BM25)

- **Status:** accepted
- **Date:** 2026-07-02

## Context

The reference design (§3, §4, §13.1) targets a Docker-Compose stack: Neo4j,
Qdrant, OpenSearch, Docling-Serve, Postgres, Redis, MinIO, Dagster. The target
deployment environment has **no Docker daemon access**, yet the system must
actually *run* end-to-end (ingest → KG → retrieval → agent → API → UI), not just
exist as code. We also need it to run on any laptop/CI with zero services.

## Decision

Introduce two interchangeable **runtime profiles** selected by
`RUNTIME_PROFILE`:

- **`embedded`** (default) — everything in-process, no server:
  - Graph (Cypher): **Kuzu** (MIT) — embedded Cypher engine, same query language
    and property-graph model as Neo4j; migrations/constraints/upsert/read
    templates are written against it.
  - Vector: **qdrant-client** in **local/on-disk** mode (Apache-2.0) — identical
    client API to the Qdrant server, so switching to a server is a URL change.
  - Keyword: **BM25** (rank-bm25, Apache-2.0) persisted under `var/bm25`.
  - Doc parsing: pypdf / pdfplumber / python-docx / python-pptx (permissive).
  - Object store / relational: local filesystem under `var/`.
- **`server`** — the docker-compose stack in `infra/` (Neo4j/Qdrant/OpenSearch/…).

Store access is behind interfaces (`GraphStore`, `VectorStore`, `KeywordStore`)
so the two profiles are swappable and the higher layers (retrieval, agent, API)
are profile-agnostic.

### Consequences

- Good: the full system runs anywhere with `make ingest && make api`; Cypher,
  vector and keyword semantics are preserved; the docker-compose deliverables and
  Neo4j migration scripts remain valid for the server profile.
- Trade-off: Kuzu ≠ Neo4j feature-for-feature (no APOC/GDS procedures) — graph
  algorithms (community/centrality/similarity) are provided via NetworkX/GDS-lite
  helpers in the embedded profile and via Neo4j GDS in the server profile.
- Scale: embedded targets the demo corpus; the 1M-entity perf target (§24.17) is
  a server-profile concern.

## Links

Task plan §3.9, §4, §13.1. Related: ADR-0003 (core stack), ADR-0006 (OSS LLMs).
