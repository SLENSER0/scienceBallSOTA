# Научный клубок — SOTA Knowledge Graph for Mining & Metallurgy R&D

A knowledge-graph platform that turns a heterogeneous corpus of mining/metallurgy
R&D documents (papers, reviews, internal reports, patents, conference decks,
experiment protocols — RU & EN) into a **single, evidence-first, verifiable
knowledge map**, and answers complex engineering questions like:

> «Какие методы обессоливания воды подходят для обогатительной фабрики, если вода
> содержит сульфаты/хлориды/Ca/Mg/Na по 200–300 мг/л, а требуемый сухой остаток
> ≤1000 мг/дм³?»

Every answer carries **sources, confidence, actualization date, geography
(отечественная/зарубежная практика), numeric ranges and gaps/contradictions**.

## Architecture

Monorepo (`apps/*`, `packages/*`, `infra/*`) with an ingestion → extraction →
knowledge-graph → retrieval → agent → API → UI pipeline.

| Layer | Target stack (docker) | **Runnable embedded default** |
|---|---|---|
| Graph (Cypher) | Neo4j + APOC/GDS | **Kuzu** (embedded Cypher) |
| Vector search | Qdrant server | **qdrant-client** (local/on-disk) |
| Keyword search | OpenSearch | **BM25** (in-process) |
| Embeddings | — | **fastembed** multilingual-MiniLM (384d, RU/EN) |
| Doc parsing | Docling Serve | pypdf / pdfplumber / python-docx / python-pptx |
| LLM | — | **OpenRouter, OSS-only** (Qwen2.5 / DeepSeek-V3 / Mistral) |
| Agent | LangGraph | LangGraph |
| API / UI | FastAPI / React+Vite | FastAPI / React+Vite |

The **embedded profile** (default, `RUNTIME_PROFILE=embedded`) runs the whole
system with no Docker daemon — see `docs/adr/0005-embedded-runtime-profile.md`.
The **server profile** uses the docker-compose stack in `infra/`.

## Features

- **Ingestion** — PDF/DOCX/PPTX/XLSX parsing (RU/EN), chunking, rule + OSS-LLM
  extraction of entities/relations/measurements with evidence spans, unit
  normalization (pint), entity resolution, evidence-first upsert; resumable,
  ~1.3s/doc.
- **Knowledge graph** — 33+ domain labels, declarative edge schema, deterministic
  IDs, provenance/versioning, generated LinkML ontology + Neo4j migrations.
- **Retrieval** — structured graph templates + vector (fastembed→Qdrant) + keyword
  (BM25) + RRF hybrid fusion + GraphRAG community summaries.
- **Agent (LangGraph)** — parse → retrieve → access-filter → synthesize a grounded,
  **cited** literature-review answer with confidence, tables, gaps, contradictions.
- **Verification** — gap analysis (9 gap types) + contradiction detection;
  every answer is evidence-first with source/confidence/geography.
- **Domain** — RU↔EN taxonomy (218 terms), numeric constraints (≤1000 мг/дм³ …),
  domestic/foreign practice, comparison tables, coverage dashboards.
- **Governance** — JWT auth + RBAC (6 roles) + row-level access, audit log,
  expert curation (edit/merge/history, protected re-ingestion), notifications,
  Markdown/JSON-LD export, SHACL shapes, FAIR metadata.
- **UI** — React/Vite workspace: chat + the *клубок* graph (d3-force), coverage,
  gaps & review, glossary, evidence inspector.

## Verified end-to-end

- All **4 mandatory acceptance queries** pass (`make demo`; report in
  `docs/eval/domain_science_ball_report.md`), with RU/EN parity, numeric filters,
  geography, contradictions and evidence.
- **Real corpus**: 60 documents ingested → 19.7k nodes / 57k rels; hybrid index
  over 3.1k chunks; gap-scan found 88 gaps + 292 contradictions; the OSS
  DeepSeek-V3 LLM answers all four queries on real data
  (`docs/eval/demo_report.md`).
- **Adversarially reviewed** (multi-agent), 15 correctness bugs fixed with
  regression tests (`docs/eval/adversarial_review_findings.md`).
- ~100 tests pass, ruff clean.

## Licensing (OSS-only)

Per the hackathon rules every component is under a permitted OSS license
(Apache-2.0 / MIT / GPL-family). This includes the **LLMs** (only Apache-2.0 /
MIT models — no Llama/Gemma). See `docs/LICENSES.md` and
`docs/adr/0006-oss-llm-and-licensing.md`. Project license: **Apache-2.0**.

## Quick start (embedded, no Docker)

```bash
make bootstrap            # uv sync --all-packages (+ frontend deps)
cp .env.example .env      # put your OPENROUTER_API_KEY
make check                # lint + format-check + tests
make ingest N=20          # parse & extract 20 corpus docs into the KG
make seed                 # seed the demo graph
make api                  # API gateway on :8000  (GET /api/v1/admin/health)
make frontend             # React UI on :3000
make demo                 # run the 4 acceptance queries end-to-end
```

## Repo layout (§6.1)

```
apps/        api-gateway agent-service ingestion-service graph-service
             search-service extraction-service curation-service frontend
packages/    kg_common kg_schema kg_extractors kg_retrievers kg_eval
infra/       docker-compose.yml neo4j/ qdrant/ opensearch/ dagster/ helm/
docs/        adr/ conventions/ domain/ eval/  + task plan & guides
third_party/ vendored OSS reference repos (study only; git-ignored)
```

See `docs/architecture.md` for the full map and `docs/FULL_SYSTEM_TASKS_science_ball.md`
for the task plan (progress tracked with `python scripts/mark_tasks.py stats`).
