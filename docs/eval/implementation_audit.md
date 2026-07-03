# Implementation audit vs. FULL_SYSTEM_TASKS spec (2026-07-03)

Eight parallel agents audited §4/§5/§6/§7/§12/§13/§14/§15 against the actual
code, each requiring file:line evidence. **Headline: the codebase is a genuinely
working, tested *embedded-profile MVP*; the spec describes a much larger
*production system*. Under strict per-bullet reading, none of the 8 audited
sections has a fully-DONE subsection — every one is PARTIAL or MISSING.**

This is not a defect in the working software (206+ tests green, all acceptance
queries pass) — it's the gap between "works end-to-end for the domain" and "every
production subsystem the blueprint enumerates is built".

## What genuinely works + is tested (embedded profile)
- Retrieval: RRF hybrid (k=60), rank-bm25 keyword, qdrant-local dense vectors,
  cross-lingual RU/EN, entity vector index, community detection + summaries.
- Extraction: rule + OSS-LLM path, unit regex + pint normalization, evidence-first
  invariant enforced, Pydantic extraction schemas + validators.
- Agent: LangGraph parse→retrieve→access→synthesize, 5 tools, cited answers,
  SSE streaming, RBAC access policy.
- Gap/contradiction: idempotent Gap/Contradiction/GapScanRun nodes, ~5 rules,
  numeric-divergence contradictions, 2D coverage matrix + absence-confidence.
- API: query/graph/evidence/gaps/curation/auth/audit/admin endpoints, e2e +
  contract tests. Security: JWT+RBAC+audit, cypher_guard, access policy.
- Infra: Dagster asset graph + schedule, docker-compose (healthchecked), CI.

## The gap (production blueprint, largely unbuilt)
Per-section, the spec enumerates a far larger surface than the MVP:
- **§4/§12**: multi-backend Qdrant-server + OpenSearch, named dense/sparse/
  multivector vectors, ScoredChunk/SearchQuery/SearchResult DTOs, weighted
  fusion + graph-proximity + evidence-quality + cross-encoder rerank, /search/*
  endpoints, reindex API, Recall@10/MRR eval.
- **§5**: Docling-Serve client, Postgres source registry, MinIO storage, upload/
  documents/ingest endpoints, section-aware chunking, parser fallback protocol,
  OCR.
- **§6**: layered rules/ml/llm/graph architecture, GLiNER + MatBERT, LlamaIndex
  PropertyGraphIndex, composition/processing/property vocab extractors,
  orchestrator, extraction golden set.
- **§7**: `kg_common/units/` materials-science subsystem — hardness/strength
  converters, property-unit policy, range validation. (hardness.py now added.)
- **§13**: 20-field ScientificAgentState, 12-node graph, intent classifier,
  entity resolver, verifier loop, Postgres checkpointer, HITL interrupt,
  streaming module, 16-tool registry.
- **§14**: microservice gateway (httpx→agent/graph/search/ingestion/curation),
  chat sessions, documents/ingest/views/facets endpoints, rate limiting,
  401-on-invalid-JWT, ErrorResponse/Paginated schemas.
- **§15**: 11 gap types (2 missing from the enum), GAP_RULES registry, lifecycle,
  3D coverage matrix, by-owner/timeline, richer contradiction heuristics.

## Note on existing marks
The §12 and §15 audits found some already-`[x]` boxes (e.g. 12.1–12.4, and the
GapType enum in 15.1) that the code does not fully bear out — a few marks from
earlier bulk passes are optimistic. New work follows a stricter bar: mark a
subsection only when its acceptance is met by working code **and** a passing test.

## Priority backlog (highest domain value first)
1. §15.3 remaining gap rules + 2 missing GapType enum values (small, high value).
2. §4.8/§12.4 weighted fusion + graph-proximity/evidence-quality scores.
3. §5 section-aware chunking + source registry (MetaStore already exists).
4. §6 composition/processing/property vocab extractors.
5. §13 verifier node + richer agent state.
