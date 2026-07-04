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

from kg_common import get_logger, make_id, uuid5_id
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
        # 'id'/'label' are managed by the store, not editable props (avoid a 500)
        changes = {k: v for k, v in changes.items() if k not in ("id", "label")}
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
        # Normalize UI verbs ("approved"/"approve"/"accept") to the canonical
        # "accepted" review state so review_status, the verified flag AND the
        # audit action (ACCEPT vs REJECT) are all recorded correctly.
        status = {
            "approved": "accepted",
            "approve": "accepted",
            "accept": "accepted",
            "reject": "rejected",
        }.get(status, status)
        self.store.upsert_node(
            node_id,
            before["label"],
            review_status=status,
            verified=(status == "accepted"),
            updated_at=self._now(),
        )
        action = CurationAction.ACCEPT if status == "accepted" else CurationAction.REJECT
        return self._record(action, node_id, before, self.store.get_node(node_id), actor, reason)

    def mark_inferred(
        self, node_id: str, *, inferred: bool = True, actor: str, reason: str = ""
    ) -> dict[str, Any]:
        """Flag a node/edge fact as human-marked inferred (dashed in UI, §5.2.3)."""
        before = self.store.get_node(node_id)
        if before is None:
            raise KeyError(node_id)
        self.store.upsert_node(
            node_id, before["label"], inferred=inferred, updated_at=self._now(), created_by=actor
        )
        return self._record(
            CurationAction.MARK_INFERRED,
            node_id,
            before,
            self.store.get_node(node_id),
            actor,
            reason or f"inferred={inferred}",
        )

    def annotate(self, node_id: str, note: str, *, actor: str) -> dict[str, Any]:
        """Attach a curator note (annotate a gap/entity/contradiction)."""
        before = self.store.get_node(node_id)
        if before is None:
            raise KeyError(node_id)
        notes = before.get("curator_notes") or ""
        merged = f"{notes}\n{actor}: {note}".strip()
        self.store.upsert_node(node_id, before["label"], curator_notes=merged[:4000])
        return self._record(
            CurationAction.ANNOTATE, node_id, before, self.store.get_node(node_id), actor, note
        )

    def add_manual_evidence(
        self,
        node_id: str,
        *,
        text: str,
        doc_id: str = "manual",
        actor: str,
        page: int | None = None,
    ) -> dict[str, Any]:
        """Curator attaches a manual evidence span to a fact (§12.2 manual-evidence)."""
        before = self.store.get_node(node_id)
        if before is None:
            raise KeyError(node_id)
        ev_id = uuid5_id("Evidence", node_id, text, actor)
        self.store.upsert_node(
            ev_id,
            "Evidence",
            text=text[:2000],
            doc_id=doc_id,
            page=page,
            source_type="manual",
            evidence_strength="expert_assertion",
            created_by=actor,
            review_status="accepted",
            verified=True,
            created_at=self._now(),
            schema_version=SCHEMA_VERSION,
        )
        self.store.upsert_edge(node_id, ev_id, "SUPPORTED_BY", created_at=self._now())
        self._record(CurationAction.MANUAL_EVIDENCE, node_id, before, None, actor, text[:80])
        return {"evidence_id": ev_id, "node_id": node_id, "action": "manual_evidence"}

    def split_entity(
        self, node_id: str, *, new_name: str, actor: str, reason: str = ""
    ) -> dict[str, Any]:
        """Split a wrongly-merged entity: create a sibling canonical (§12.2 split)."""
        orig = self.store.get_node(node_id)
        if orig is None:
            raise KeyError(node_id)
        new_id = make_id(orig["label"], new_name)
        self.store.upsert_node(
            new_id,
            orig["label"],
            name=new_name,
            canonical_name=new_name,
            review_status="corrected",
            verified=True,
            created_by=actor,
            created_at=self._now(),
            schema_version=SCHEMA_VERSION,
        )
        self._record(
            CurationAction.SPLIT, node_id, orig, self.store.get_node(new_id), actor, reason
        )
        return {"original_id": node_id, "new_id": new_id, "action": "split"}

    def resolve_contradiction(
        self, contradiction_id: str, *, resolution: str, actor: str, reason: str = ""
    ) -> dict[str, Any]:
        """Curator resolves a contradiction, recording the chosen resolution (§16/§24.20)."""
        before = self.store.get_node(contradiction_id)
        if before is None or before.get("label") != "Contradiction":
            raise KeyError(f"contradiction {contradiction_id} not found")
        self.store.upsert_node(
            contradiction_id,
            "Contradiction",
            review_status="resolved",
            resolution=resolution,
            verified=True,
            updated_at=self._now(),
        )
        return self._record(
            CurationAction.RESOLVE_CONTRADICTION,
            contradiction_id,
            before,
            self.store.get_node(contradiction_id),
            actor,
            reason or resolution,
        )

    def set_practice_type(self, node_id: str, practice_type: str, *, actor: str) -> dict[str, Any]:
        """Mark a solution as domestic/foreign practice (§24.20)."""
        before = self.store.get_node(node_id)
        if before is None:
            raise KeyError(node_id)
        self.store.upsert_node(
            node_id, before["label"], practice_type=practice_type, updated_at=self._now()
        )
        domestic = practice_type.lower() in {"russia", "domestic", "отечественная", "россия"}
        action = (
            CurationAction.MARK_AS_DOMESTIC_PRACTICE
            if domestic
            else CurationAction.MARK_AS_FOREIGN_PRACTICE
        )
        return self._record(
            action, node_id, before, self.store.get_node(node_id), actor, practice_type
        )

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
