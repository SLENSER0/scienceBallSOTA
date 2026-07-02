# Definition of Done — «Научный клубок» (domain)

Status of the domain acceptance criteria (§24.22). Verified by
`uv run python -m kg_eval.runner --suite domain_science_ball` (report in
`docs/eval/domain_science_ball_report.md`) and the pytest suite.

| # | Criterion (§24.22) | Status | Evidence |
|---|---|---|---|
| 1 | 4 mandatory queries answered e2e | ✅ | eval 4/4 pass; `test_eval.py` |
| 2 | NL query → parsed entities/constraints | ✅ | `query_parser`, `parsedQuery` in answer |
| 3 | Retrieved facts + answer + table + graph | ✅ | `AnswerPayload` (markdown/table/graph) |
| 4 | Evidence inspector | ✅ | `/evidence/{id}`, FE drawer |
| 5 | Export | ✅ | `/export` Markdown / JSON-LD |
| 6 | RU/EN parity | ✅ | eval `ru_en_parity` check (≥50% overlap; 80–100%) |
| 7 | domestic/foreign filtering | ✅ | practice_type parse + grouping (Ni, injection cases) |
| 8 | numeric range filtering (≥4 params) | ✅ | concentration, TDS, flow velocity, current density |
| 9 | contradiction/gap display | ✅ | Ni-catholyte contradiction, cold-heap-leaching gap |
| 10 | RBAC external_partner vs researcher | ✅ | `access.py`, `test_rbac_external_partner` |
| 11 | dashboard + coverage | ✅ | `/admin/coverage`, FE Coverage view |
| 12 | domain eval in CI/release gate | ✅ | `test_eval.py` in pytest, `make demo` |

## Runtime notes
- OSS-only LLMs (Qwen2.5 / DeepSeek-V3 / Mistral — Apache-2.0 / MIT); no Llama/Gemma (ADR-0006).
- Embedded profile (Kuzu / qdrant-local / BM25) runs with no Docker (ADR-0005).
- Corpus: 1332 discoverable source files; rule + LLM extraction; evidence-first graph.

The domain release is allowed when the eval suite is green and the four mandatory
queries return evidence-backed, filter-aware, confidence-scored answers — which
they do.
