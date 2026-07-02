# Naming conventions

- **Python import packages:** `snake_case`, `kg_*` for shared packages
  (`kg_common`, `kg_schema`, `kg_extractors`, `kg_retrievers`, `kg_eval`), service
  packages match the app dir (`api_gateway`, `agent_service`, …).
- **Distribution names:** `kebab-case` (`kg-common`, `api-gateway`).
- **Graph labels:** `PascalCase` (`Material`, `ProcessingRegime`) — see
  `kg_schema.labels.NodeLabel`.
- **Relationship types:** `UPPER_SNAKE_CASE` (`OF_PROPERTY`) — `kg_schema.RelType`.
- **Deterministic IDs:** `<prefix>:<slug|hash>` (`material:al-cu-2024`) —
  `kg_common.ids`.
- **Enum values:** `snake_case` string values.
- **Frontend TS types:** `PascalCase`; JSON payload fields are `camelCase`
  (Pydantic `CamelModel` alias generator keeps parity).
