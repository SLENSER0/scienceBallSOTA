# third_party/ — vendored OSS reference repositories (study only)

Repos listed in the task plan (§1.14 / §21) are cloned here **for study and
reference**, not modified in place. They are **git-ignored** (only this README and
`CATALOG.md` are tracked) — they are large and are not part of our source.

## Conventions

- One directory per repo: `third_party/<name>/`.
- Pinned to a specific tag/commit where practical (see `scripts/vendor.sh`).
- Do not edit vendored code in place; wrap/adapt behind our interfaces.
- Lint/type/test tooling excludes `third_party/` (see `pyproject.toml`).

## Usage

```bash
make vendor            # clone/update the reference set (idempotent)
scripts/vendor.sh core # clone only the core reference repos
```

See `CATALOG.md` for the full list with git URLs and which plan section uses each.
