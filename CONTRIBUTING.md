# Contributing

## Workflow

- Trunk-based with short-lived feature branches. **No direct pushes to `main`**
  for feature work (hotfixes/hackathon cadence excepted).
- Run `make check` (lint + format-check + tests) before every PR.
- New code ships with tests. Bug fixes ship with a regression test.

## Code style

- Python: **ruff** (lint + format), line length 100, `from __future__ import
  annotations`, type hints everywhere; **mypy** for core packages.
- Frontend: **eslint** + **prettier** (printWidth 100, single quotes).

## Commit messages — Conventional Commits

`type(scope): summary` where `type ∈ {feat, fix, docs, refactor, test, chore,
ci, build}` and `scope` is a service/package name, e.g. `feat(kg_schema): add
domain labels`. See `docs/conventions/commits.md`.

## Licensing (mandatory)

Only OSS-licensed code/models may be introduced — Apache-2.0 / MIT / GPL-family
(see `docs/LICENSES.md`, ADR-0006). New dependencies must have their license
recorded in `docs/LICENSES.md`. **No Llama/Gemma models.**

## Architecture decisions

Non-trivial choices get an ADR in `docs/adr/` (MADR format, `0000-template.md`).

## Marking task progress

`docs/FULL_SYSTEM_TASKS_science_ball.md` is the plan. Update it with
`python scripts/mark_tasks.py section <id>...` when a section's work lands and is
verified; `python scripts/mark_tasks.py stats` shows progress.
