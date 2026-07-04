"""Server-profile graph store on Neo4j (§3.1 / §8) — drop-in for KuzuGraphStore.

Zero-schema mirror of :class:`~kg_retrievers.graph_store.KuzuGraphStore`: the same
generic model — one ``:Node`` label carrying an ``id`` + ``label`` + arbitrary
properties, and one ``:Rel`` relationship carrying a ``type`` property + provenance
— but every property is written as a **native** Neo4j value (Neo4j is schemaless)
instead of being split into typed columns plus a ``props`` JSON blob.

Серверный профиль хранилища графа: тот же публичный интерфейс, что и у Kuzu,
поэтому вызывающий код (retrievers, GraphRAG) не отличает бэкенды. DTO-маппинг
(:meth:`node_to_dto`) переиспользуется из Kuzu без изменений.

Design notes:
- props are sanitised before write — ``str/int/float/bool`` and lists of scalars
  stay native, everything else (dict/nested) is ``json.dumps``-ed, ``None`` dropped;
- one ``driver.session()`` is opened per call (the driver is thread-safe);
- ``batch()`` is a documented no-op — Neo4j auto-commits each statement, and the
  bulk helpers already coalesce writes via ``UNWIND``.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from neo4j import GraphDatabase, Record

from kg_common import GraphEdge, GraphNode, GraphResponse, get_logger

# node_to_dto is a model-agnostic @staticmethod over a plain dict — reuse verbatim.
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("neo4j_store")

_Scalar = (str, int, float, bool)


def _sanitize(value: Any) -> Any:
    """Coerce a Python value into a Neo4j-storable native property (§8).

    Keep scalars and lists-of-scalars as-is; JSON-encode anything else so it can be
    written as a plain string. Callers drop ``None`` before reaching here.
    """
    if isinstance(value, (str, int, float)):  # bool is a subclass of int
        return value
    if isinstance(value, list) and all(isinstance(x, _Scalar) for x in value):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


class Neo4jGraphStore:
    """Read-write graph store backed by a live Neo4j server (server profile)."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._driver.verify_connectivity()
        # Stable connection identifier — mirrors KuzuGraphStore.db_path so callers
        # that key caches on ``store.db_path`` work for either backend (§2 drop-in).
        self.db_path = uri
        self.ensure_schema()

    # -- schema ----------------------------------------------------------
    def ensure_schema(self) -> None:
        """Guarantee ``:Node(id)`` uniqueness (idempotent, safe to re-run)."""
        with self._driver.session() as session:
            session.run(
                "CREATE CONSTRAINT node_id_unique IF NOT EXISTS FOR (n:Node) REQUIRE n.id IS UNIQUE"
            ).consume()

    # -- write -----------------------------------------------------------
    def upsert_node(self, node_id: str, label: str, **props: Any) -> None:
        """MERGE a node by id; ``label`` + every prop become native properties."""
        clean: dict[str, Any] = {"label": label}
        for k, v in props.items():
            if v is None or k in ("id", "label"):
                continue  # 'id' identifies the node; 'label' is positional
            clean[k] = _sanitize(v)
        with self._driver.session() as session:
            session.run(
                "MERGE (n:Node {id:$id}) SET n += $props",
                {"id": node_id, "props": clean},
            ).consume()

    def upsert_edge(self, src: str, dst: str, rel_type: str, **props: Any) -> None:
        """MERGE ``(src)-[:Rel {type}]->(dst)`` carrying native provenance props."""
        clean: dict[str, Any] = {}
        for k, v in props.items():
            if v is None:
                continue
            clean[k] = _sanitize(v)
        with self._driver.session() as session:
            session.run(
                "MATCH (x:Node {id:$a}), (y:Node {id:$b}) "
                "MERGE (x)-[r:Rel {type:$rtype}]->(y) "
                "SET r += $props, r.type = $rtype",
                {"a": src, "b": dst, "rtype": rel_type, "props": clean},
            ).consume()

    def execute(self, cypher: str, params: dict[str, Any] | None = None) -> list[Record]:
        """Run a Cypher statement and return the fully-consumed list of records."""
        with self._driver.session() as session:
            return list(session.run(cypher, params or {}))

    @contextlib.contextmanager
    def batch(self):  # type: ignore[no-untyped-def]
        """No-op batch context (§8).

        Neo4j auto-commits each statement and every method already opens its own
        session, so there is no shared transaction to group. Kept for interface
        parity with Kuzu; use :meth:`bulk_upsert_nodes` / :meth:`bulk_upsert_edges`
        for fast bulk writes.
        """
        yield

    # -- bulk (fast migration via UNWIND) --------------------------------
    def bulk_upsert_nodes(self, rows: Iterable[Any]) -> None:
        """UNWIND-MERGE many nodes. Rows are ``(id, label, props)`` or dicts."""
        batch: list[dict[str, Any]] = []
        for row in rows:
            nid, label, props = _node_row(row)
            clean: dict[str, Any] = {"label": label}
            for k, v in (props or {}).items():
                if v is None or k in ("id", "label"):
                    continue
                clean[k] = _sanitize(v)
            batch.append({"id": nid, "props": clean})
        if not batch:
            return
        with self._driver.session() as session:
            session.run(
                "UNWIND $rows AS row MERGE (n:Node {id: row.id}) SET n += row.props",
                {"rows": batch},
            ).consume()

    def bulk_upsert_edges(self, rows: Iterable[Any]) -> None:
        """UNWIND-MERGE many edges. Rows are ``(src, dst, type, props)`` or dicts."""
        batch: list[dict[str, Any]] = []
        for row in rows:
            src, dst, rtype, props = _edge_row(row)
            clean: dict[str, Any] = {}
            for k, v in (props or {}).items():
                if v is None:
                    continue
                clean[k] = _sanitize(v)
            batch.append({"src": src, "dst": dst, "rtype": rtype, "props": clean})
        if not batch:
            return
        with self._driver.session() as session:
            session.run(
                "UNWIND $rows AS row "
                "MATCH (x:Node {id: row.src}), (y:Node {id: row.dst}) "
                "MERGE (x)-[r:Rel {type: row.rtype}]->(y) "
                "SET r += row.props, r.type = row.rtype",
                {"rows": batch},
            ).consume()

    # -- read ------------------------------------------------------------
    def rows(self, cypher: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
        """Return ``list(record.values())`` per row; a returned node stays a Node."""
        return [list(rec.values()) for rec in self.execute(cypher, params)]

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        rows = self.rows("MATCH (n:Node {id:$id}) RETURN n", {"id": node_id})
        if not rows:
            return None
        return self._node_dict(rows[0][0])

    @staticmethod
    def _node_dict(raw: Any) -> dict[str, Any]:
        """Flatten a neo4j ``Node`` OR a plain dict into non-None props."""
        items = dict(raw)  # neo4j.graph.Node is a Mapping, so dict() covers both
        d = {k: v for k, v in items.items() if v is not None and not k.startswith("_")}
        props = d.pop("props", None)  # tolerate a legacy JSON blob if one exists
        if isinstance(props, str) and props:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                d.update(json.loads(props))
        return d

    def is_reviewed(self, node_id: str) -> bool:
        """True if a node's factual fields are protected from auto-overwrite (§3.7)."""
        nd = self.get_node(node_id)
        return bool(nd and nd.get("review_status") in {"accepted", "corrected"})

    def upsert_node_guarded(self, node_id: str, label: str, **props: Any) -> bool:
        """Upsert unless the node is reviewed (§3.7). Returns False if skipped."""
        if self.is_reviewed(node_id):
            return False
        self.upsert_node(node_id, label, **props)
        return True

    def delete_node(self, node_id: str) -> None:
        with self._driver.session() as session:
            session.run("MATCH (n:Node {id:$id}) DETACH DELETE n", {"id": node_id}).consume()

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

    # A query answer's graph payload is capped: a 1800-node subgraph is unrenderable
    # in the UI and (pre-fix) cost one round-trip PER node to hydrate. Seeds are kept
    # whole; expansion fills up to the cap.
    _MAX_SUBGRAPH_NODES = 160
    _MAX_SEEDS = 70  # keep room for 1-hop neighbours so the graph stays connected

    def subgraph_from_ids(self, node_ids: list[str], expand: int = 1) -> GraphResponse:
        """Build a payload from seed node ids, optionally expanding N hops (bounded)."""
        seeds = list(dict.fromkeys(node_ids))  # de-dup, keep order
        ids: list[str] = seeds[: self._MAX_SEEDS]
        seen: set[str] = set(ids)
        if expand > 0 and ids and len(ids) < self._MAX_SUBGRAPH_NODES:
            # Expand from the (capped) seeds so their neighbours connect the graph;
            # without this the payload is a scatter of unconnected seed nodes.
            for r in self.rows(
                f"MATCH (a:Node)-[:Rel*1..{max(1, min(expand, 3))}]-(b:Node) "
                "WHERE a.id IN $ids RETURN DISTINCT b.id LIMIT $lim",
                {"ids": ids, "lim": self._MAX_SUBGRAPH_NODES},
            ):
                if r[0] not in seen:
                    seen.add(r[0])
                    ids.append(r[0])
                    if len(ids) >= self._MAX_SUBGRAPH_NODES:
                        break
        # Hydrate ALL nodes in ONE query — was N+1 (get_node per id → ~1800 round-trips).
        nodes: list[GraphNode] = []
        for r in self.rows("MATCH (n:Node) WHERE n.id IN $ids RETURN n", {"ids": ids}):
            nd = self._node_dict(r[0])
            if nd.get("id"):
                nodes.append(self.node_to_dto(nd))
        return GraphResponse(nodes=nodes, edges=self.edges_among(set(ids)))

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
                    evidence_ids=_evidence_ids(eids),
                )
            )
        return edges

    # DTO mapping is identical to Kuzu — reuse the model-agnostic staticmethod.
    node_to_dto = staticmethod(KuzuGraphStore.node_to_dto)

    def close(self) -> None:
        self._driver.close()


def _evidence_ids(eids: Any) -> list[str] | None:
    """Normalise evidence_ids stored as a native list OR a JSON string."""
    if isinstance(eids, list):
        return eids
    if isinstance(eids, str) and eids:
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            return json.loads(eids)
    return None


def _node_row(row: Any) -> tuple[str, str, dict[str, Any]]:
    """Unpack a bulk node row: dict ``{id,label,props}`` or ``(id, label, props?)``."""
    if isinstance(row, Mapping):
        return row["id"], row["label"], dict(row.get("props") or {})
    nid, label = row[0], row[1]
    props = row[2] if len(row) > 2 else {}
    return nid, label, dict(props or {})


def _edge_row(row: Any) -> tuple[str, str, str, dict[str, Any]]:
    """Unpack a bulk edge row: dict ``{src,dst,type,props}`` or ``(src,dst,type,props?)``."""
    if isinstance(row, Mapping):
        return row["src"], row["dst"], row["type"], dict(row.get("props") or {})
    src, dst, rtype = row[0], row[1], row[2]
    props = row[3] if len(row) > 3 else {}
    return src, dst, rtype, dict(props or {})
