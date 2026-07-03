"""Embedded Cypher graph store on Kuzu (§3 / ADR-0005).

Heterogeneous KG modelled with one generic ``Node`` table (typed columns for the
filters that matter — numeric ranges, geography, time, review — plus a JSON
``props`` catch-all) and one generic ``Rel`` table carrying provenance. This keeps
the 33+ ontology labels flexible while staying Cypher-queryable and swappable for
a Neo4j-backed store in the server profile.

Key Kuzu constraints respected here:
- the primary key (``id``) is set by the MERGE pattern, never by ``SET``;
- one read-write connection per process (guarded by a lock).
"""

from __future__ import annotations

import contextlib
import json
import threading
from pathlib import Path
from typing import Any

import kuzu

from kg_common import GraphEdge, GraphNode, GraphResponse, get_logger

_log = get_logger("graph_store")

# Typed node columns used for structured filtering (everything else -> props JSON).
NODE_COLUMNS: list[tuple[str, str]] = [
    ("id", "STRING"),
    ("label", "STRING"),
    ("name", "STRING"),
    ("canonical_name", "STRING"),
    ("aliases_text", "STRING"),
    ("text", "STRING"),
    ("value_normalized", "DOUBLE"),
    ("normalized_unit", "STRING"),
    ("value_raw", "STRING"),
    ("unit", "STRING"),
    ("temperature_c", "DOUBLE"),
    ("time_h", "DOUBLE"),
    ("confidence", "DOUBLE"),
    ("year", "INT64"),
    ("review_status", "STRING"),
    ("evidence_strength", "STRING"),
    ("verification_level", "STRING"),
    ("practice_type", "STRING"),
    ("country", "STRING"),
    ("region", "STRING"),
    ("climate_zone", "STRING"),
    ("domain", "STRING"),
    ("operation", "STRING"),
    ("property_name", "STRING"),
    ("material_class", "STRING"),
    ("gap_type", "STRING"),
    ("polarity", "STRING"),
    ("doc_id", "STRING"),
    ("page", "INT64"),
    ("source_type", "STRING"),
    ("lang", "STRING"),
    ("verified", "BOOLEAN"),
    ("date_actualized", "STRING"),
    ("valid_until", "STRING"),
    ("created_at", "STRING"),
    ("updated_at", "STRING"),
    ("schema_version", "STRING"),
    ("extractor_run_id", "STRING"),
    ("community_id", "INT64"),
    ("degree", "INT64"),
    ("pagerank", "DOUBLE"),
    ("confidentiality_level", "STRING"),
    ("props", "STRING"),
]
_NODE_COL_NAMES = {c for c, _ in NODE_COLUMNS}

REL_COLUMNS: list[tuple[str, str]] = [
    ("type", "STRING"),
    ("confidence", "DOUBLE"),
    ("extractor_run_id", "STRING"),
    ("created_at", "STRING"),
    ("schema_version", "STRING"),
    ("evidence_ids", "STRING"),
    ("inferred", "BOOLEAN"),
    ("contradicted", "BOOLEAN"),
    # Measurable-value-in-mention signal (§33/N2): set on prose Document→Chunk→
    # (MENTIONS)→Property edges at ingest (see ingestion pipeline + D1). NULL on
    # structural/catalog edges and pre-N2 edges — the absence value gate treats a
    # missing flag as "unknown" and never downgrades on it. Typed so it is
    # Cypher-queryable and upserted idempotently on both ON CREATE / ON MATCH.
    ("value_present", "BOOLEAN"),
    ("props", "STRING"),
]
_REL_COL_NAMES = {c for c, _ in REL_COLUMNS}


class KuzuGraphStore:
    """Read-write graph store backed by an embedded Kuzu database."""

    def __init__(self, db_path: str, *, read_only: bool = False) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._read_only = read_only
        self._db = kuzu.Database(db_path, read_only=read_only)
        self._conn = kuzu.Connection(self._db)
        self._lock = threading.RLock()
        if not read_only:
            self.ensure_schema()

    # -- schema ----------------------------------------------------------
    def ensure_schema(self) -> None:
        with self._lock:
            existing = self._table_names()
            if "Node" not in existing:
                cols = ", ".join(f"{c} {t}" for c, t in NODE_COLUMNS)
                self._conn.execute(f"CREATE NODE TABLE Node({cols}, PRIMARY KEY(id))")
            if "Rel" not in existing:
                cols = ", ".join(f"{c} {t}" for c, t in REL_COLUMNS)
                self._conn.execute(f"CREATE REL TABLE Rel(FROM Node TO Node, {cols})")

    def _table_names(self) -> set[str]:
        try:
            res = self._conn.execute("CALL show_tables() RETURN name")
            names = set()
            while res.has_next():  # type: ignore[union-attr]
                names.add(res.get_next()[0])  # type: ignore[union-attr]
            return names
        except Exception:  # fresh db
            return set()

    # -- write -----------------------------------------------------------
    def upsert_node(self, node_id: str, label: str, **props: Any) -> None:
        """MERGE a node by id. Typed keys go to columns; the rest into props JSON."""
        cols: dict[str, Any] = {"label": label}
        extra: dict[str, Any] = {}
        for k, v in props.items():
            if v is None or k in ("id", "label"):
                continue  # 'id' is the PK (set by MERGE, never SET); 'label' is positional
            if k in _NODE_COL_NAMES and k != "props":
                cols[k] = v
            else:
                extra[k] = v
        if extra:
            cols["props"] = json.dumps(extra, ensure_ascii=False, default=str)
        set_clause = ", ".join(f"n.{k}=${k}" for k in cols)
        params = {"id": node_id, **cols}
        with self._lock:
            self._conn.execute(
                f"MERGE (n:Node {{id:$id}}) ON CREATE SET {set_clause} ON MATCH SET {set_clause}",
                params,
            )

    def upsert_edge(self, src: str, dst: str, rel_type: str, **props: Any) -> None:
        cols: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        for k, v in props.items():
            if v is None:
                continue
            if k == "evidence_ids" and isinstance(v, list):
                cols[k] = json.dumps(v)
            elif k in _REL_COL_NAMES and k != "props":
                cols[k] = v
            else:
                extra[k] = v
        if extra:
            cols["props"] = json.dumps(extra, ensure_ascii=False, default=str)
        extra_sets = "".join(f", r.{k}=${k}" for k in cols)
        params = {"a": src, "b": dst, "rtype": rel_type, **cols}
        with self._lock:
            self._conn.execute(
                "MATCH (x:Node {id:$a}), (y:Node {id:$b}) "
                "MERGE (x)-[r:Rel {type:$rtype}]->(y) "
                f"ON CREATE SET r.type=$rtype{extra_sets} "
                f"ON MATCH SET r.type=$rtype{extra_sets}",
                params,
            )

    def execute(self, cypher: str, params: dict[str, Any] | None = None) -> kuzu.QueryResult:
        with self._lock:
            return self._conn.execute(cypher, params or {})  # type: ignore[return-value]

    @contextlib.contextmanager
    def batch(self):  # type: ignore[no-untyped-def]
        """Group writes into one Kuzu transaction (~1.4x faster bulk upsert)."""
        with self._lock:
            self._conn.execute("BEGIN TRANSACTION")
            try:
                yield
                self._conn.execute("COMMIT")
            except Exception:
                with contextlib.suppress(Exception):
                    self._conn.execute("ROLLBACK")
                raise

    # -- read ------------------------------------------------------------
    def rows(self, cypher: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
        res = self.execute(cypher, params)
        out: list[list[Any]] = []
        while res.has_next():  # type: ignore[union-attr]
            out.append(res.get_next())  # type: ignore[union-attr]
        return out

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        res = self.execute("MATCH (n:Node {id:$id}) RETURN n", {"id": node_id})
        if not res.has_next():  # type: ignore[union-attr]
            return None
        return self._node_dict(res.get_next()[0])  # type: ignore[union-attr]

    @staticmethod
    def _node_dict(raw: dict[str, Any]) -> dict[str, Any]:
        d = {k: v for k, v in raw.items() if v is not None and not k.startswith("_")}
        props = d.pop("props", None)
        if props:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                d.update(json.loads(props))
        return d

    def is_reviewed(self, node_id: str) -> bool:
        """True if a node's factual fields are protected from auto-overwrite (§3.7)."""
        nd = self.get_node(node_id)
        return bool(nd and nd.get("review_status") in {"accepted", "corrected"})

    def upsert_node_guarded(self, node_id: str, label: str, **props: Any) -> bool:
        """Upsert but never overwrite a reviewed node's fields (§3.7 re-ingestion).

        Returns True if written, False if skipped because the node is reviewed.
        """
        if self.is_reviewed(node_id):
            return False
        self.upsert_node(node_id, label, **props)
        return True

    def delete_node(self, node_id: str) -> None:
        with self._lock:
            self._conn.execute("MATCH (n:Node {id:$id}) DETACH DELETE n", {"id": node_id})

    def counts(self) -> dict[str, int]:
        nodes = self.rows("MATCH (n:Node) RETURN count(n)")
        rels = self.rows("MATCH ()-[r:Rel]->() RETURN count(r)")
        return {"nodes": nodes[0][0] if nodes else 0, "rels": rels[0][0] if rels else 0}

    def counts_by_label(self) -> dict[str, int]:
        rows = self.rows("MATCH (n:Node) RETURN n.label, count(n) ORDER BY count(n) DESC")
        return {r[0]: r[1] for r in rows}

    # -- graph payload (§5.3) -------------------------------------------
    def neighbors(self, node_id: str, depth: int = 1, limit: int = 300) -> GraphResponse:
        depth = max(1, min(depth, 4))
        rows = self.rows(
            f"MATCH (a:Node {{id:$id}})-[:Rel*1..{depth}]-(b:Node) RETURN DISTINCT b LIMIT {limit}",
            {"id": node_id},
        )
        nodes: dict[str, GraphNode] = {}
        ids: set[str] = set()
        center = self.get_node(node_id)
        if center:
            nodes[center["id"]] = self.node_to_dto(center)
            ids.add(center["id"])
        for r in rows:
            nd = self._node_dict(r[0])
            if nd.get("id"):
                nodes[nd["id"]] = self.node_to_dto(nd)
                ids.add(nd["id"])
        return GraphResponse(nodes=list(nodes.values()), edges=self.edges_among(ids))

    def subgraph_from_ids(self, node_ids: list[str], expand: int = 1) -> GraphResponse:
        """Build a payload from seed node ids, optionally expanding N hops."""
        ids: set[str] = set(node_ids)
        if expand > 0 and node_ids:
            for r in self.rows(
                f"MATCH (a:Node)-[:Rel*1..{max(1, min(expand, 3))}]-(b:Node) "
                "WHERE a.id IN $ids RETURN DISTINCT b.id LIMIT 500",
                {"ids": node_ids},
            ):
                ids.add(r[0])
        nodes: list[GraphNode] = []
        for nid in ids:
            nd = self.get_node(nid)
            if nd:
                nodes.append(self.node_to_dto(nd))
        return GraphResponse(nodes=nodes, edges=self.edges_among(ids))

    def edges_among(self, ids: set[str]) -> list[GraphEdge]:
        if not ids:
            return []
        rows = self.rows(
            "MATCH (a:Node)-[r:Rel]->(b:Node) WHERE a.id IN $ids AND b.id IN $ids "
            "RETURN a.id, r.type, b.id, r.confidence, r.evidence_ids, r.contradicted, r.inferred",
            {"ids": list(ids)},
        )
        edges: list[GraphEdge] = []
        for a, t, b, conf, eids, contra, inf in rows:
            edges.append(
                GraphEdge(
                    id=f"{a}|{t}|{b}",
                    source=a,
                    target=b,
                    label=t,
                    type=t,
                    confidence=conf,
                    contradicted=contra,
                    inferred=inf,
                    evidence_ids=json.loads(eids) if isinstance(eids, str) and eids else None,
                )
            )
        return edges

    @staticmethod
    def node_to_dto(nd: dict[str, Any]) -> GraphNode:
        return GraphNode(
            id=nd["id"],
            label=nd.get("name") or nd.get("canonical_name") or nd["id"],
            type=nd.get("label", "Entity"),
            confidence=nd.get("confidence"),
            verified=nd.get("verified"),
            community_id=nd.get("community_id"),
            properties={
                k: v
                for k, v in nd.items()
                if k not in {"id", "name", "label", "confidence", "verified"}
            },
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()
            self._db.close()
