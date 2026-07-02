# Secret management

- **Local dev:** `.env` (git-ignored). Copy from `.env.example`. Never commit real
  secrets. `detect-secrets`/`gitleaks` run in pre-commit and CI.
- **Prod:** HashiCorp Vault or K8s/Docker secrets. Vault path convention:
  `secret/kg/<env>/<service>` (e.g. `secret/kg/prod/api-gateway`).
- **Rotation:** `OPENROUTER_API_KEY`, `JWT_SECRET`, store passwords rotate per
  policy; app reads them via `kg_common.Settings` (env-injected).
- **OSS-model policy (§24.14):** restricted corpus data is only sent to the
  approved OSS model allowlist; no proprietary endpoints.
- `make check-env` diffs `.env` keys against `.env.example` to catch drift.
