# ADR 0001: Python package/workspace manager — uv

- **Status:** accepted
- **Date:** 2026-07-02

## Context

The monorepo hosts 5 shared packages (`packages/*`) and 7 Python services
(`apps/*`) that must share one resolved dependency set and a single `.venv` for
fast local dev and reproducible CI.

## Considered options

- **uv** (Astral) — Rust, native workspaces, extremely fast, single lockfile.
- **Poetry** — mature, but slower, weaker monorepo/workspace story.
- **pip + pip-tools** — manual, no workspace concept.

## Decision

Use **uv** with `[tool.uv.workspace]` (members `packages/*`, `apps/*`, excluding
`apps/frontend`). `make bootstrap` = `uv sync --all-packages`. Lockfile `uv.lock`
is committed; `uv sync --frozen` reproduces the environment.

### Consequences

- Good: sub-second resolves, one venv, workspace `tool.uv.sources` wiring of the
  local `kg-*` packages, Apache-2.0/MIT-licensed toolchain.
- Trade-off: uv is younger than Poetry; pinned via `.tool-versions`.

## Links

Task plan §1.2. Alternative Poetry documented here as rejected.
