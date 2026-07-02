#!/usr/bin/env python3
"""Runner for the demo seed graph (§3.17). Idempotent.

Embedded profile → Kuzu at ``KUZU_DB_PATH``. Delegates to
``kg_retrievers.seed.build_seed_graph``.
"""

from __future__ import annotations

from kg_retrievers.seed import main

if __name__ == "__main__":
    main()
