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
