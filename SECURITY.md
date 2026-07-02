# Security policy

## Reporting a vulnerability

Email the maintainer (see `.github/CODEOWNERS`) with a description and
reproduction. Do not open a public issue for undisclosed vulnerabilities.

## Handling of sensitive data

- The corpus may contain internal/restricted reports (§24.14). RBAC + row-level
  filtering restrict access; the agent never emits restricted evidence to
  unauthorized roles.
- Restricted data is only sent to the approved **OSS model allowlist** (ADR-0006).
- Secrets: see `docs/secrets.md`. `gitleaks`/`detect-secrets` gate commits and CI.
