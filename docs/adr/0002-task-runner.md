# ADR 0002: Task runner — Make

- **Status:** accepted
- **Date:** 2026-07-02

## Decision

Use a self-documenting **Makefile** as the single task entry point
(`make help`, `bootstrap`, `check`, `ingest`, `api`, `demo`, …). It is ubiquitous
on Linux/macOS/CI and needs no extra install.

`Taskfile.yml` (go-task) was considered for nicer cross-platform/Windows support
but rejected to avoid an extra dependency; can be added later without changing the
Make targets.

## Links

Task plan §1.11.
