# Commit conventions — Conventional Commits

`type(scope): summary`

- **type**: `feat | fix | docs | refactor | test | chore | ci | build`
- **scope**: service/package name, e.g. `kg_schema`, `agent-service`, `ingestion`
- **summary**: imperative, ≤ 72 chars

Examples:
- `feat(kg_schema): add domain labels for mining-metallurgy`
- `fix(ingestion): handle merged table cells in pdfplumber parser`
- `docs(adr): record OSS-only LLM decision (0006)`
