# API contract sync (backend ↔ frontend)

- **Source of truth:** `packages/kg_common/dto.py` (Pydantic) + `packages/kg_schema`
  (labels/relationships/enums). FastAPI exposes the OpenAPI schema at
  `/openapi.json` and `/api/v1/graph/schema` (labels/rels/enums/version).
- **Frontend types** (`GraphResponse`, `GraphNode`, `GraphEdge`, `ChatStreamEvent`
  in §5.3) must stay in parity with the Pydantic DTOs. Field JSON names are
  **camelCase** on both sides (Pydantic `CamelModel` alias generator).
- **Enforcement:** generate TS types from OpenAPI (`openapi-typescript`) or a PR
  checklist item; a contract test asserts `/api/v1/graph/schema` lists all 33
  labels and every `RelType`.
- **Breaking changes:** bump API version prefix and note in an ADR.
