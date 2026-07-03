# Демо-walkthrough «Научный клубок» (§19.11)

One-command bootstrap (embedded profile — no Docker):

```bash
make demo          # seeds the graph, detects communities, scans gaps, prints creds + URL
# → API on http://localhost:8000  (docs at /docs)
```

`make demo` runs `infra/demo/up.sh`, which builds the seed graph (7 acceptance
scenarios incl. a `Gap` and a `Contradiction`), runs community detection + a gap
scan, and starts the API gateway. Demo credentials are **role names** (embedded
JWT, demo-only — never prod): `admin`, `curator`, `researcher`, `analyst`,
`external_partner`.

## Steps (each with the expected result)

1. **Login per role** — `POST /api/v1/auth/login {"username":"researcher","role":"researcher"}` → a JWT. Repeat for `external_partner`.
2. **Access differs by role (RBAC §19.3)** — run the same query as `researcher` and `external_partner`:
   `POST /api/v1/query {"query":"циркуляция католита электроэкстракция никеля","use_llm":false}`.
   The partner sees **fewer citations** (restricted/internal sources filtered) — verified by `test_rbac_via_jwt`.
3. **Top flow «что делали по X при Y и эффект на Z?» (§19 demo p.6)** —
   `POST /api/v1/query {"query":"методы обессоливания воды сульфаты 200–300 мг/л TDS ≤1000 мг/дм³","use_llm":false}`.
   The answer carries **numbers + conditions + sources + evidence + a graph payload** (`answerMarkdown`, `citations[].evidence`, `graph.nodes/edges`, `confidence`) — verified by `test_golden_flow_end_to_end`.
4. **Graph explorer** — `POST /api/v1/graph/subgraph {"node_ids":["material:nickel"],"expand":1}` → a `GraphResponse` subgraph; `GET /api/v1/graph/path?source=…&target=…` for shortest paths.
5. **Evidence inspector (§5.2.6)** — take a citation's `evidenceId` → `GET /api/v1/evidence/{id}` (doc/page/text/strength); `GET /api/v1/evidence/by-node/{fact}` lists a fact's sources.
6. **Gap dashboard (§15)** — `POST /api/v1/gaps/scan` → `{gaps, contradictions}`; `GET /api/v1/gaps/ranked` (priority + next-experiment hint); `GET /api/v1/admin/absence-map`; `GET /api/v1/contradictions` shows the seeded catholyte-velocity contradiction.
7. **Curation (§16)** — as `curator`: `POST /api/v1/entities/{id}/status`, `/mark-inferred`, `/manual-evidence`, `/contradictions/{id}/resolve`; then `GET /api/v1/entities/{id}/history` shows the decision trail.
8. **Coverage / analytics** — `GET /api/v1/admin/coverage`, `/coverage-matrix`, `/community-hierarchy`, `/retrieval-eval`, `/graph-algos`.

## Sanitized / safe to show

Demo runs under the embedded profile in `var/` (no external services); demo
credentials are role names only, distinct from any production secret
(`JWT_SECRET` guarded by `require_prod_secret` outside local). For the server
profile use `COMPOSE_PROFILES=demo docker compose -f infra/docker-compose.yml up`.
