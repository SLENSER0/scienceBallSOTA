"""Smoke test: train a trivial Splink model on DuckDB + dedupe (§8.1).

Run: ``python -m kg_er.scripts.smoke_splink``. Exits non-zero if the DuckDB
backend / training / prediction path is broken. Deterministic (fixed seed).
"""

from __future__ import annotations

import sys

from kg_er import resolve


def main() -> int:
    mentions = [
        {"unique_id": "m1", "name": "nickel", "formula": "Ni"},
        {"unique_id": "m2", "name": "nickle", "formula": "Ni"},  # typo dupe of m1
        {"unique_id": "m3", "name": "copper", "formula": "Cu"},
        {"unique_id": "m4", "name": "copper", "formula": "Cu"},  # exact dupe of m3
        {"unique_id": "m5", "name": "platinum", "formula": "Pt"},
    ]
    result = resolve("Material", mentions, threshold=0.5, trained_at="smoke")
    print("summary:", result.summary())
    for p in result.proposals:
        print("  proposal:", p.as_dict())
    # Expect at least the exact copper dupe to cluster.
    clustered = {m for p in result.proposals for m in p.members}
    if not clustered:
        print("SMOKE FAIL: no clusters formed", file=sys.stderr)
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
