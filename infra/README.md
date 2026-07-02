# infra/ — deployment (§2 / §13.1)

Default runtime is the **embedded** profile (no Docker, ADR-0005). This directory
provisions the **server** profile.

| Path | Purpose |
|---|---|
| `docker-compose.yml` | full server stack: Neo4j, Qdrant, OpenSearch, Postgres, Valkey, MinIO, Docling-Serve + app services (§13.1) |
| `neo4j/` | Neo4j config, plugins (APOC/GDS), migrations (§3.10-3.13), seed, backup docs |
| `qdrant/`, `opensearch/` | vector / keyword service configs |
| `helm/` | Kubernetes chart (Deployment/Service, health probes, secret injection) |
| `dagster/` | orchestration assets + weekly corpus-refresh schedule (§9) |

## Quick start (server profile)

```bash
cp .env.example .env        # set OPENROUTER_API_KEY (OSS models only)
make up                     # docker compose up -d
# apply Neo4j migrations
for f in neo4j/migrations/000*.cypher; do cypher-shell -u neo4j -p password < "$f"; done
```

## Ops

- **Backup/restore**: `scripts/backup.sh` (embedded var/) or `neo4j-admin dump/load`.
- **Healthchecks**: every compose service has one; app services expose
  `/api/v1/admin/health`.
- **Secrets**: `docs/secrets.md` (Vault path `secret/kg/<env>/<service>`).
- **CI/CD**: `.github/workflows/{ci,cd}.yml` (lint/type/test; build+push images; helm lint).
- **Observability**: OTel hooks (`kg_common.telemetry`), `/admin/metrics`, `/admin/audit`.
