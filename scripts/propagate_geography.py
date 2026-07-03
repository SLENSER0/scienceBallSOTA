"""Propagate source geography + dates from Document → Evidence → Measurement (Neo4j).

The adversarial audit (2026-07) found country/practice_type/year classified only on
Document/Paper nodes (161/66k), leaving 0/23,414 Evidence and ~0/23,422 Measurement
facts classifiable — so geographic + temporal filtering had nothing to filter on.

This backfills, over the existing server-profile graph, four provenance props onto every
Evidence and Measurement from its parent Document:
  - ``country``        (e.g. "russia" / "china")
  - ``practice_type``  ("russia" / "cis" / "foreign" / "global")
  - ``source_year``    (Document.year — publication vintage, drives time-range filtering)
  - ``source_date``    (Document.created_at — freshness / date-of-actualization)

Graph shape (generic :Node/:Rel, semantic type in ``r.type``):
  Document -[HAS_CHUNK]-> Chunk <-[FROM_CHUNK]- Evidence <-[HAS_EVIDENCE]- Measurement

Idempotent (plain SET) and batched via CALL-in-transactions. Run under RUNTIME_PROFILE=server.
"""

from __future__ import annotations

import os

from neo4j import GraphDatabase

_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
_AUTH = (os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", "password"))

# Evidence inherits from the Document whose Chunk it cites.
_EVIDENCE = """
CALL {
  MATCH (d:Node {label:'Document'})-[:Rel]->(c:Node {label:'Chunk'})<-[:Rel]-(e:Node {label:'Evidence'})
  WHERE d.country IS NOT NULL AND e.country IS NULL
  SET e.country = d.country,
      e.practice_type = d.practice_type,
      e.source_year = d.year,
      e.source_date = d.created_at
  RETURN e
} IN TRANSACTIONS OF 2000 ROWS
RETURN count(*) AS n
"""

# Measurement inherits through its supporting Evidence.
_MEASUREMENT = """
CALL {
  MATCH (e:Node {label:'Evidence'})<-[:Rel]-(m:Node {label:'Measurement'})
  WHERE e.country IS NOT NULL AND m.country IS NULL
  SET m.country = e.country,
      m.practice_type = e.practice_type,
      m.source_year = e.source_year,
      m.source_date = e.source_date
  RETURN m
} IN TRANSACTIONS OF 2000 ROWS
RETURN count(*) AS n
"""

_REPORT = """
MATCH (n:Node)
WHERE n.label IN ['Evidence','Measurement']
RETURN n.label AS label,
       count(*) AS total,
       count(n.practice_type) AS classified,
       sum(CASE WHEN n.practice_type='russia' THEN 1 ELSE 0 END) AS russia,
       sum(CASE WHEN n.practice_type='foreign' THEN 1 ELSE 0 END) AS foreign
ORDER BY label
"""


def main() -> None:
    drv = GraphDatabase.driver(_URI, auth=_AUTH)
    try:
        with drv.session() as s:
            # CALL {...} IN TRANSACTIONS must run in auto-commit mode (session.run).
            n_ev = s.run(_EVIDENCE).single()["n"]
            print(f"evidence classified: {n_ev}")
            n_m = s.run(_MEASUREMENT).single()["n"]
            print(f"measurement classified: {n_m}")
            print("--- distribution ---")
            for r in s.run(_REPORT):
                print(
                    f"  {r['label']}: total={r['total']} classified={r['classified']} "
                    f"russia={r['russia']} foreign={r['foreign']}"
                )
    finally:
        drv.close()


if __name__ == "__main__":
    main()
