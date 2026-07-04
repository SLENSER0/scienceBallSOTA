# Third-party license register

Project license: **Apache-2.0** (`LICENSE`, `NOTICE`). Every dependency and model
below is under a license permitted by hackathon rule §7.5 (AGPLv3 / GPLv3 /
LGPLv3 / EPL / MPL / Apache-2.0 / MIT — permissive BSD/ISC treated as MIT-class).

## LLMs (weights, served via OpenRouter — OSS-only)

| Model | License | Use |
|---|---|---|
| qwen/qwen3.6-35b-a3b | Apache-2.0 | extraction / fast (default) |
| deepseek/deepseek-v4-flash | MIT | agent synthesis (default) |
| z-ai/glm-5.2 | MIT | synthesis quality mode / deep-research supervisor |
| qwen/qwen3-235b-a22b | Apache-2.0 | heavy synthesis (alt) |
| mistralai/mistral-small-24b-instruct-2501 | Apache-2.0 | alt |
| minimax/minimax-m3 | ⚠ MiniMax-Community (NOT permissive) | multimodal deep-research (OPTIONAL only) |

**Excluded** (license not permitted): meta-llama/* (Llama Community License),
google/gemma-* (Gemma License), nvidia/nemotron-* (OpenMDW).
**Policy caveat:** `minimax/minimax-m3` is MiniMax-Community (not MIT/Apache) — allowed
only for the optional multimodal role, never the core text path, under strict OSS rules.

## Embedding model

| Model | License |
|---|---|
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | Apache-2.0 |

## Python runtime dependencies

| Package | License |
|---|---|
| kuzu | MIT |
| qdrant-client | Apache-2.0 |
| fastembed | Apache-2.0 |
| rank-bm25 | Apache-2.0 |
| numpy | BSD-3-Clause |
| fastapi / starlette | MIT / BSD-3-Clause |
| uvicorn | BSD-3-Clause |
| pydantic / pydantic-settings | MIT |
| langgraph / langchain-core / langchain-openai | MIT |
| openai (client SDK) | Apache-2.0 |
| pypdf | BSD-3-Clause |
| pdfplumber | MIT |
| python-docx | MIT |
| python-pptx | MIT |
| openpyxl | MIT |
| pint | BSD-3-Clause |
| rapidfuzz | MIT |
| structlog | MIT / Apache-2.0 |
| orjson | Apache-2.0 / MIT |
| xlsxwriter | BSD-2-Clause |

## Server-profile services (docker)

| Service | License |
|---|---|
| Neo4j Community | GPLv3 |
| Qdrant | Apache-2.0 |
| OpenSearch | Apache-2.0 |
| PostgreSQL | PostgreSQL License (permissive) |
| Redis | RSALv2/SSPL (>=7.4) — use Valkey (BSD) as OSS drop-in |
| MinIO | AGPLv3 |
| Dagster | Apache-2.0 |

> Note: for a strictly OSS server profile prefer **Valkey** (BSD) over recent
> Redis. Redis ≤7.2 is BSD-3-Clause.

## Frontend dependencies

React, Vite, Tailwind, Zustand, @tanstack/*, Reagraph, ECharts, react-markdown —
all MIT / Apache-2.0. Pinned versions and licenses are emitted by
`pnpm licenses list` in CI.
