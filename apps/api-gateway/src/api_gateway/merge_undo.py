"""Undo merge + reversibility surface for the curation UI (§8.9).

Каждое слияние сущностей (``CurationService.merge_entities``, §8.9) записывает
``CurationEvent{action:merge}`` со снимком ``before`` — полными свойствами
поглощённого (drop) узла — до его удаления. Этот снимок и есть обратная ссылка
``merged_from``: по нему исходную сущность можно восстановить. Модуль читает
события слияния из графа, отдаёт их как обратимые записи для UI курирования и
выполняет откат (undo) по ``event_id``, воссоздавая drop-узел из ``before`` и
записывая компенсирующее ``CurationEvent{action:split}`` (полная auditability,
ничего не теряется). Работает поверх общего интерфейса graph-store — и Kuzu
(embedded), и Neo4j (server-профиль :8000).

Every entity merge (``CurationService.merge_entities``, §8.9) records a
``CurationEvent{action:merge}`` whose ``before`` snapshot holds the full props of
the absorbed (drop) node captured *before* deletion. That snapshot is the
reversibility anchor (``merged_from``): the losing entity can be reconstructed
from it. This module lists merge events as reversible records for the curation
UI and performs the undo by ``event_id`` — recreating the drop node from
``before`` and recording a compensating ``CurationEvent{action:split}`` (nothing
is deleted, the audit trail only grows). Backend-agnostic (Kuzu / Neo4j server).
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from typing import Any

from kg_common import get_logger, uuid5_id

_log = get_logger("merge_undo")
SCHEMA_VERSION = "0.1.0"


class MergeUndoService:
    """List reversible merges and undo them from their ``before`` snapshot (§8.9)."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    # -- snapshot helpers -------------------------------------------------
    @staticmethod
    def _parse_snapshot(raw: Any) -> dict[str, Any]:
        """Parse a ``before``/``after`` CurationEvent field into a dict (best-effort)."""
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    return obj
        return {}

    def _reversible(self, ev: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        """Return ``(can_undo, reason_if_not, drop_snapshot)`` for a merge event."""
        if ev.get("undone"):
            return False, "already undone", {}
        drop = self._parse_snapshot(ev.get("before"))
        drop_id = drop.get("id")
        if not drop_id or not drop.get("label"):
            return False, "snapshot missing id/label (truncated?)", drop
        if self.store.get_node(str(drop_id)) is not None:
            return False, "restored entity already exists", drop
        return True, "", drop

    # -- read -------------------------------------------------------------
    def list_merges(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent merge events as reversible records, newest first (§8.9)."""
        rows = self.store.rows(
            "MATCH (e:Node) WHERE e.label='CurationEvent' AND e.action='merge' "
            f"RETURN e.id, e.created_at ORDER BY e.created_at DESC LIMIT {int(limit)}"
        )
        out: list[dict[str, Any]] = []
        for eid, created in rows:
            ev = self.store.get_node(eid) or {}
            can_undo, why, drop = self._reversible(ev)
            keep_id = ev.get("target_id")
            keep = self.store.get_node(str(keep_id)) if keep_id else None
            after = self._parse_snapshot(ev.get("after"))
            out.append(
                {
                    "event_id": eid,
                    "actor": ev.get("actor_id"),
                    "reason": ev.get("reason"),
                    "created_at": ev.get("created_at") or created,
                    "keep_id": keep_id,
                    "keep_name": (keep or {}).get("name") or after.get("name"),
                    "keep_label": (keep or {}).get("label") or after.get("label"),
                    "keep_exists": keep is not None,
                    "dropped_id": drop.get("id"),
                    "dropped_name": drop.get("name") or drop.get("canonical_name"),
                    "dropped_label": drop.get("label"),
                    "undone": bool(ev.get("undone")),
                    "undone_by": ev.get("undone_by"),
                    "undone_at": ev.get("undone_at"),
                    "reversible": can_undo,
                    "blocked_reason": why or None,
                }
            )
        return out

    # -- write ------------------------------------------------------------
    def _record_split(
        self,
        keep_id: str,
        restored_id: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        *,
        actor: str,
        reason: str,
        origin_event: str,
    ) -> str:
        """Write the compensating ``CurationEvent{action:split}`` for the undo (§12.3)."""
        ev_id = uuid5_id("CurationEvent", keep_id, "split", self._now())
        self.store.upsert_node(
            ev_id,
            "CurationEvent",
            name=f"split {keep_id}",
            actor_id=actor,
            action="split",
            target_type="node",
            target_id=keep_id,
            before=json.dumps(before, ensure_ascii=False, default=str)[:4000],
            after=json.dumps(after, ensure_ascii=False, default=str)[:4000],
            reason=reason,
            undo_of=origin_event,
            created_at=self._now(),
            schema_version=SCHEMA_VERSION,
        )
        # Link the compensating event to both sides so history() surfaces it on each.
        self.store.upsert_edge(ev_id, keep_id, "CHANGED", created_at=self._now())
        self.store.upsert_edge(ev_id, restored_id, "CHANGED", created_at=self._now())
        return ev_id

    def undo_merge(
        self, event_id: str, *, actor: str = "curator", reason: str = ""
    ) -> dict[str, Any]:
        """Reverse a merge by ``event_id``: restore the dropped entity (§8.9).

        Recreates the absorbed node from the merge event's ``before`` snapshot,
        stamps the merge event ``undone=true`` for idempotency, and records a
        compensating ``CurationEvent{action:split}``. Edges that the merge relinked
        onto the surviving node are *not* torn back off (their original owner is not
        recorded) — the survivor keeps them; the restored node comes back standalone.

        :raises KeyError: no CurationEvent with ``event_id``.
        :raises ValueError: event is not a merge, is already undone, or its snapshot
            cannot rebuild the entity (missing id/label, or the id is live again).
        """
        ev = self.store.get_node(event_id)
        if ev is None or ev.get("label") != "CurationEvent":
            raise KeyError(f"merge event {event_id} not found")
        if ev.get("action") != "merge":
            raise ValueError(f"event {event_id} is action={ev.get('action')!r}, not merge")
        can_undo, why, drop = self._reversible(ev)
        if not can_undo:
            raise ValueError(f"cannot undo merge {event_id}: {why}")

        drop_id = str(drop["id"])
        label = str(drop["label"])
        # Restore the node verbatim from the snapshot, plus a provenance stamp.
        props = {k: v for k, v in drop.items() if k not in ("id", "label")}
        props.update(
            restored_from_merge=event_id,
            restored_by=actor,
            restored_at=self._now(),
        )
        self.store.upsert_node(drop_id, label, **props)

        keep_id = str(ev.get("target_id") or "")
        keep_after = self.store.get_node(keep_id) if keep_id else None

        undo_reason = reason or f"undo of merge {event_id}"
        comp_id = self._record_split(
            keep_id or drop_id,
            drop_id,
            before=keep_after,
            after=self.store.get_node(drop_id),
            actor=actor,
            reason=undo_reason,
            origin_event=event_id,
        )
        # Stamp the original merge event so it can't be replayed (idempotency).
        self.store.upsert_node(
            event_id,
            "CurationEvent",
            undone=True,
            undone_by=actor,
            undone_at=self._now(),
            undo_event_id=comp_id,
        )
        _log.info("merge.undo", event=event_id, restored=drop_id, keep=keep_id, actor=actor)
        return {
            "event_id": event_id,
            "undo_event_id": comp_id,
            "restored_id": drop_id,
            "restored_label": label,
            "keep_id": keep_id or None,
            "action": "undo_merge",
        }
