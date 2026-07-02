# ADR 0006: OSS-only LLMs and license compliance

- **Status:** accepted
- **Date:** 2026-07-02

## Context

Hackathon rule §7.5 permits only these OSS licenses: **AGPLv3, GPLv3, LGPLv3,
EPL 1.0, MPL, Apache-2.0, MIT** (with the usual attribution / copyleft
conditions). This constrains BOTH our software dependencies AND the LLM weights
we use. The user further required: *"only open-source LLMs — any, as long as they
are open source."*

## Decision

### LLMs — Apache-2.0 / MIT weights only, served via OpenRouter

| Role | Model | License |
|---|---|---|
| Extraction (default) | `qwen/qwen-2.5-7b-instruct` | Apache-2.0 |
| Synthesis / agent | `deepseek/deepseek-chat-v3-0324` | MIT |
| Alternates | `mistralai/mistral-small-24b-instruct-2501`, `qwen/qwen3-235b-a22b` | Apache-2.0 |

**Explicitly excluded:** Llama (Llama Community License) and Gemma (Gemma
License) — neither is in the permitted list. All model IDs are configurable
(`LLM_MODEL_*`); operators must keep them within the permitted-license set.

### Embeddings — Apache-2.0

`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (Apache-2.0),
strong RU↔EN cross-lingual similarity (validated 0.83 on domain terms).

### Software dependencies — all permissive

Kuzu (MIT), qdrant-client / fastembed / rank-bm25 (Apache-2.0), FastAPI /
pydantic / langgraph / pypdf / python-docx / python-pptx / openpyxl (MIT/BSD),
pint (BSD). Full register in `docs/LICENSES.md`. Server-profile Neo4j Community
is GPLv3 (also permitted).

### Project license

**Apache-2.0** (attribution + note changes) — see `LICENSE` / `NOTICE`.

## Consequences

- Good: fully compliant with §7.5; data never sent to a non-OSS model.
- Trade-off: we forgo some proprietary SOTA models; Qwen/DeepSeek are strong on
  RU/EN technical text so quality impact is small.
- Security (§24.14): a policy allowlist ensures restricted corpus data is only
  sent to approved OSS models.

## Links

Hackathon rules §7.5–7.8; task plan §19, §24.14, §24.21.
