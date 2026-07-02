# Operations runbook

## Bootstrap (embedded, no Docker)

```bash
make bootstrap          # uv sync --all-packages (+ frontend pnpm install)
cp .env.example .env    # set OPENROUTER_API_KEY (OSS models only)
make check              # ruff + format-check + pytest (~100 tests)
```

## Data pipeline

```bash
make seed                        # build the demo graph (idempotent)
make ingest N=120                # parse+extract+upsert N docs (resumable)
python -m ingestion_service.cli ingest --limit 0 --workers 4   # ALL docs (resumes via var/ingest_done.txt)
make index                       # build vector (Qdrant) + BM25 indexes over chunks
make gap-scan                    # detect gaps + contradictions
make schema-gen                  # regenerate LinkML ontology + Neo4j migrations
```

Ingestion is **resumable** (`var/ingest_done.txt`) and **idempotent** (file-hash
dedup + deterministic-ID MERGE). Use `--max-mb 8` to skip very large books for a
fast representative sample. Reviewed/expert-corrected fields are protected from
re-ingestion overwrite.

## Serve

```bash
make api        # FastAPI on :8000  (GET /api/v1/admin/health)
make frontend   # React/Vite on :3000
make demo       # run the 4 acceptance queries end-to-end (eval)
python scripts/demo_report.py   # LLM answers on the live store → docs/eval/demo_report.md
```

## Server profile (Docker/K8s)

```bash
make up                                  # docker compose (Neo4j/Qdrant/OpenSearch/…)
helm install klubok infra/helm -f infra/helm/values.yaml   # Kubernetes
dagster dev -f infra/dagster/definitions.py                # orchestration (optional)
```

## Observability & governance

- `/api/v1/admin/metrics` — per-route counts/latency.
- `/api/v1/admin/lineage` — extractor/gap-scan run provenance.
- `/api/v1/admin/audit` — action audit log (privileged roles).
- `/api/v1/admin/coverage` — per-domain knowledge coverage / risk zones.

## Backup / restore

Embedded stores live under `var/` (Kuzu `var/kuzu`, Qdrant `var/qdrant`, BM25
`var/bm25`). Back up the directory. Server-profile Neo4j: `neo4j-admin database
dump/load` (see `infra/neo4j/README.md`).
