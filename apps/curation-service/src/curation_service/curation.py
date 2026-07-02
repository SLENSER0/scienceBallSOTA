"""Curation workflow: expert edits, decision history, review queue (§16 / §24.20).

Every change records a CurationEvent (actor, before/after, reason) and marks the
target ``review_status='corrected'`` so re-ingestion won't overwrite it
(``upsert_node_guarded``, §3.7). Supports edit / accept / reject / add-alias /
merge, plus a review queue and per-entity history.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from kg_common import get_logger, uuid5_id
from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.enums import CurationAction

_log = get_logger("curation")
SCHEMA_VERSION = "0.1.0"


class CurationService:
    name = "curation-service"

    def __init__(self, store: KuzuGraphStore) -> None:
        self.store = store

    def health(self) -> dict[str, str]:
        return {"status": "ok", "service": self.name}

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    def _record(
        self,
        action: str,
        target_id: str,
        before: dict | None,
        after: dict | None,
        actor: str,
        reason: str,
    ) -> dict[str, Any]:
        ev_id = uuid5_id("CurationEvent", target_id, action, self._now())
        self.store.upsert_node(
            ev_id,
            "CurationEvent",
            name=f"{action} {target_id}",
            actor_id=actor,
            action=action,
            target_type="node",
            target_id=target_id,
            before=json.dumps(before, ensure_ascii=False, default=str)[:4000],
            after=json.dumps(after, ensure_ascii=False, default=str)[:4000],
            reason=reason,
            created_at=self._now(),
            schema_version=SCHEMA_VERSION,
        )
        self.store.upsert_edge(ev_id, target_id, "CHANGED", created_at=self._now())
        return {"event_id": ev_id, "action": action, "target_id": target_id}

    # -- edits -----------------------------------------------------------
    def edit_node(
        self, node_id: str, changes: dict[str, Any], *, actor: str, reason: str = ""
    ) -> dict[str, Any]:
        before = self.store.get_node(node_id)
        if before is None:
            raise KeyError(f"node {node_id} not found")
        self.store.upsert_node(
            node_id,
            before["label"],
            **{
                **changes,
                "review_status": "corrected",
                "verified": True,
                "updated_at": self._now(),
                "created_by": actor,
            },
        )
        after = self.store.get_node(node_id)
        _log.info("curation.edit", node=node_id, actor=actor)
        return self._record(CurationAction.CORRECT, node_id, before, after, actor, reason)

    def set_status(
        self, node_id: str, status: str, *, actor: str, reason: str = ""
    ) -> dict[str, Any]:
        before = self.store.get_node(node_id)
        if before is None:
            raise KeyError(node_id)
        self.store.upsert_node(
            node_id,
            before["label"],
            review_status=status,
            verified=(status == "accepted"),
            updated_at=self._now(),
        )
        action = CurationAction.ACCEPT if status == "accepted" else CurationAction.REJECT
        return self._record(action, node_id, before, self.store.get_node(node_id), actor, reason)

    def add_alias(self, node_id: str, alias: str, *, actor: str) -> dict[str, Any]:
        before = self.store.get_node(node_id)
        if before is None:
            raise KeyError(node_id)
        aliases = before.get("aliases_text") or ""
        merged = "|".join(dict.fromkeys([*aliases.split("|"), alias]).keys()).strip("|")
        self.store.upsert_node(node_id, before["label"], aliases_text=merged)
        return self._record(
            CurationAction.ALIAS_ADD,
            node_id,
            before,
            self.store.get_node(node_id),
            actor,
            f"alias:{alias}",
        )

    def merge_entities(
        self, keep_id: str, drop_id: str, *, actor: str, reason: str = ""
    ) -> dict[str, Any]:
        keep = self.store.get_node(keep_id)
        drop = self.store.get_node(drop_id)
        if keep is None or drop is None:
            raise KeyError(f"{keep_id} or {drop_id} not found")
        # relink drop's edges onto keep
        out_edges = self.store.rows(
            "MATCH (:Node {id:$id})-[r:Rel]->(b:Node) RETURN r.type, b.id", {"id": drop_id}
        )
        in_edges = self.store.rows(
            "MATCH (a:Node)-[r:Rel]->(:Node {id:$id}) RETURN a.id, r.type", {"id": drop_id}
        )
        for rtype, bid in out_edges:
            if bid != keep_id:
                self.store.upsert_edge(keep_id, bid, rtype, created_at=self._now())
        for aid, rtype in in_edges:
            if aid != keep_id:
                self.store.upsert_edge(aid, keep_id, rtype, created_at=self._now())
        # fold aliases
        self.add_alias(keep_id, drop.get("name") or drop_id, actor=actor)
        self.store.delete_node(drop_id)
        return self._record(
            CurationAction.MERGE, keep_id, drop, keep, actor, reason or f"merged {drop_id}"
        )

    # -- review queue / history -----------------------------------------
    def review_queue(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.store.rows(
            "MATCH (n:Node) WHERE (n.label='Gap' AND n.review_status='pending') "
            "OR (n.label='Measurement' AND n.confidence < 0.6) "
            "OR (n.label IN ['Claim','KnowledgeClaim','Recommendation'] "
            "AND n.review_status='pending') "
            f"RETURN n.id, n.label, n.name, n.review_status, n.confidence LIMIT {int(limit)}"
        )
        return [
            {"id": r[0], "label": r[1], "name": r[2], "review_status": r[3], "confidence": r[4]}
            for r in rows
        ]

    def history(self, node_id: str) -> list[dict[str, Any]]:
        # action/actor_id/reason live in the node's props JSON, so hydrate via get_node.
        rows = self.store.rows(
            "MATCH (e:Node)-[:Rel]->(t:Node {id:$id}) WHERE e.label='CurationEvent' "
            "RETURN e.id, e.created_at ORDER BY e.created_at DESC",
            {"id": node_id},
        )
        out: list[dict[str, Any]] = []
        for eid, created in rows:
            nd = self.store.get_node(eid) or {}
            out.append(
                {
                    "action": nd.get("action"),
                    "actor": nd.get("actor_id"),
                    "reason": nd.get("reason"),
                    "at": nd.get("created_at") or created,
                }
            )
        return out


def create_app(store: KuzuGraphStore | None = None) -> CurationService:
    if store is None:
        from kg_common import get_settings

        store = KuzuGraphStore(get_settings().kuzu_db_path)
    return CurationService(store)
