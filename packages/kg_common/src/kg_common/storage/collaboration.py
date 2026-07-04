"""Collaboration store — comments, mentions, shared investigations, notifications (§23.32).

Turns the read-only KG explorer into a *team* tool. Persists four kinds of
per-team state over the same backend-agnostic SQLAlchemy design as
:class:`~kg_common.storage.saved_views.ViewStore` (reuses the shared engine +
``MetaData`` and dialect-native ``INSERT ... ON CONFLICT DO UPDATE``, so re-saving
by primary key is an idempotent UPSERT):

* **comments** — threaded notes attached to any graph target
  (``Entity``/``Experiment``/``Evidence``/``Gap``/``Answer``); a comment carries a
  lifecycle ``status`` (``draft``/``in_review``/``resolved``/``archived``), an
  optional ``parent_id`` (reply threading), extracted ``@mentions`` and an
  optional ``investigation_id`` binding it to a shared investigation. Comments are
  **never** counted as factual evidence unless explicitly ``promoted`` (manual
  promoted-status, §10.8 audit/provenance).
* **investigations** — a saved, shared "investigation" workspace: a named bundle
  of entities, filters, a graph view, free-form notes, an answer-history log,
  members and a lifecycle status.
* **notifications** — a per-user notification center: ``mentioned``,
  ``assigned_review``, ``evidence_corrected``, ``gap_closed`` and thread
  ``reply``/``comment`` events, each with a read flag.
* **activity** — an append-only activity feed scoped by ``project`` (lab), so a
  team can see who did what around the graph.

The store is pure persistence + notification fan-out; it holds no graph reads, so
it is trivially unit-testable and reusable from the API router. Dict/list payloads
are serialised as JSON text so the schema is portable across SQLite and Postgres.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, Integer, String, Table, and_, select

from kg_common.storage.sql import SqlMetaStore, _dialect_insert, _metadata

# --------------------------------------------------------------------------- #
# Schema (§23.32)                                                              #
# --------------------------------------------------------------------------- #
collab_comments = Table(
    "collab_comments",
    _metadata,
    Column("comment_id", String, primary_key=True),
    Column("target_type", String, nullable=False, default=""),
    Column("target_id", String, nullable=False, default=""),
    Column("author", String, nullable=False, default=""),
    Column("body", String, nullable=False, default=""),
    Column("status", String, nullable=False, default="draft"),
    Column("parent_id", String, nullable=False, default=""),
    Column("investigation_id", String, nullable=False, default=""),
    Column("project", String, nullable=False, default=""),
    Column("mentions_json", String, nullable=False, default="[]"),
    Column("promoted", Integer, nullable=False, default=0),
    Column("created_at", String, nullable=False, default=""),
    Column("updated_at", String, nullable=False, default=""),
)

collab_investigations = Table(
    "collab_investigations",
    _metadata,
    Column("investigation_id", String, primary_key=True),
    Column("owner", String, nullable=False, default=""),
    Column("title", String, nullable=False, default=""),
    Column("notes", String, nullable=False, default=""),
    Column("status", String, nullable=False, default="draft"),
    Column("project", String, nullable=False, default=""),
    Column("entities_json", String, nullable=False, default="[]"),
    Column("filters_json", String, nullable=False, default="{}"),
    Column("view_json", String, nullable=False, default="{}"),
    Column("answers_json", String, nullable=False, default="[]"),
    Column("members_json", String, nullable=False, default="[]"),
    Column("created_at", String, nullable=False, default=""),
    Column("updated_at", String, nullable=False, default=""),
)

collab_notifications = Table(
    "collab_notifications",
    _metadata,
    Column("notif_id", String, primary_key=True),
    Column("user_id", String, nullable=False, default=""),
    Column("kind", String, nullable=False, default=""),
    Column("text", String, nullable=False, default=""),
    Column("actor", String, nullable=False, default=""),
    Column("target_type", String, nullable=False, default=""),
    Column("target_id", String, nullable=False, default=""),
    Column("investigation_id", String, nullable=False, default=""),
    Column("read", Integer, nullable=False, default=0),
    Column("created_at", String, nullable=False, default=""),
)

collab_activity = Table(
    "collab_activity",
    _metadata,
    Column("activity_id", String, primary_key=True),
    Column("actor", String, nullable=False, default=""),
    Column("verb", String, nullable=False, default=""),
    Column("target_type", String, nullable=False, default=""),
    Column("target_id", String, nullable=False, default=""),
    Column("project", String, nullable=False, default=""),
    Column("summary", String, nullable=False, default=""),
    Column("created_at", String, nullable=False, default=""),
)

# Lifecycle statuses shared by comments and investigations (§23.32).
COMMENT_STATUSES = ("draft", "in_review", "resolved", "archived")
INVESTIGATION_STATUSES = ("draft", "in_review", "resolved", "archived")
NOTIFICATION_KINDS = (
    "mentioned",
    "assigned_review",
    "evidence_corrected",
    "gap_closed",
    "reply",
    "comment",
)

# ``@user`` / ``@lab:name`` tokens: letters, digits, dot, dash, underscore, slash, colon.
_MENTION_RE = re.compile(r"@([A-Za-z0-9_./:\-]+)")


def _now() -> str:
    """Current UTC timestamp as an ISO-8601 string (portable across backends)."""
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex[:12]}"


def extract_mentions(body: str) -> list[str]:
    """Return the distinct ``@handle`` mentions in ``body`` (order-preserving).

    A handle keeps its optional ``lab:`` prefix (``@lab:mining`` → ``lab:mining``)
    so the notification fan-out can route lab mentions differently from user ones.
    Trailing punctuation is stripped so ``@alice.`` at a sentence end resolves to
    ``alice``.
    """
    seen: list[str] = []
    for raw in _MENTION_RE.findall(body or ""):
        handle = raw.rstrip(".-/:")
        if handle and handle not in seen:
            seen.append(handle)
    return seen


# --------------------------------------------------------------------------- #
# Dataclasses                                                                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Comment:
    """One comment attached to a graph target (§23.32)."""

    comment_id: str
    target_type: str = ""
    target_id: str = ""
    author: str = ""
    body: str = ""
    status: str = "draft"
    parent_id: str = ""
    investigation_id: str = ""
    project: str = ""
    mentions: list[str] = field(default_factory=list)
    promoted: bool = False
    created_at: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "comment_id": self.comment_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "author": self.author,
            "body": self.body,
            "status": self.status,
            "parent_id": self.parent_id,
            "investigation_id": self.investigation_id,
            "project": self.project,
            "mentions": list(self.mentions),
            "promoted": self.promoted,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class Investigation:
    """A shared investigation workspace (§23.32)."""

    investigation_id: str
    owner: str = ""
    title: str = ""
    notes: str = ""
    status: str = "draft"
    project: str = ""
    entities: list[Any] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    view: dict[str, Any] = field(default_factory=dict)
    answers: list[Any] = field(default_factory=list)
    members: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "investigation_id": self.investigation_id,
            "owner": self.owner,
            "title": self.title,
            "notes": self.notes,
            "status": self.status,
            "project": self.project,
            "entities": list(self.entities),
            "filters": dict(self.filters),
            "view": dict(self.view),
            "answers": list(self.answers),
            "members": list(self.members),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class Notification:
    """A single notification-center entry (§23.32)."""

    notif_id: str
    user_id: str = ""
    kind: str = ""
    text: str = ""
    actor: str = ""
    target_type: str = ""
    target_id: str = ""
    investigation_id: str = ""
    read: bool = False
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "notif_id": self.notif_id,
            "user_id": self.user_id,
            "kind": self.kind,
            "text": self.text,
            "actor": self.actor,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "investigation_id": self.investigation_id,
            "read": self.read,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class Activity:
    """One activity-feed event (§23.32)."""

    activity_id: str
    actor: str = ""
    verb: str = ""
    target_type: str = ""
    target_id: str = ""
    project: str = ""
    summary: str = ""
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "actor": self.actor,
            "verb": self.verb,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "project": self.project,
            "summary": self.summary,
            "created_at": self.created_at,
        }


# --------------------------------------------------------------------------- #
# Store                                                                        #
# --------------------------------------------------------------------------- #
class CollaborationStore:
    """Comments / investigations / notifications / activity over any SQLAlchemy URL."""

    def __init__(self, url: str = "sqlite:///:memory:") -> None:
        self._store = SqlMetaStore(url)  # reuse engine + shared MetaData
        self.engine = self._store.engine
        self._insert = _dialect_insert(self.engine)

    def migrate(self) -> None:
        """Idempotently create all collaboration tables (rollback-safe)."""
        _metadata.create_all(self.engine)

    # -- notifications (internal fan-out) --------------------------------- #
    def notify(
        self,
        user_id: str,
        kind: str,
        text: str,
        *,
        actor: str = "",
        target_type: str = "",
        target_id: str = "",
        investigation_id: str = "",
    ) -> Notification:
        """Create one notification for ``user_id`` (skips self-notification).

        Returns the stored :class:`Notification`. A user is never notified about
        their own action (``actor == user_id`` → the row is still created only if
        the caller wants an explicit self-note; here we simply skip it and return a
        transient, unsaved record so callers can fan out blindly).
        """
        rec = Notification(
            notif_id=_new_id("notif"),
            user_id=user_id,
            kind=kind,
            text=text,
            actor=actor,
            target_type=target_type,
            target_id=target_id,
            investigation_id=investigation_id,
            read=False,
            created_at=_now(),
        )
        if not user_id or user_id == actor:
            return rec  # do not persist self-notifications
        with self.engine.begin() as conn:
            conn.execute(
                self._insert(collab_notifications).values(
                    notif_id=rec.notif_id,
                    user_id=rec.user_id,
                    kind=rec.kind,
                    text=rec.text,
                    actor=rec.actor,
                    target_type=rec.target_type,
                    target_id=rec.target_id,
                    investigation_id=rec.investigation_id,
                    read=0,
                    created_at=rec.created_at,
                )
            )
        return rec

    def list_notifications(
        self, user_id: str, *, unread_only: bool = False, limit: int = 100
    ) -> list[Notification]:
        """A user's notifications, newest first."""
        cond = collab_notifications.c.user_id == user_id
        if unread_only:
            cond = and_(cond, collab_notifications.c.read == 0)
        q = (
            select(collab_notifications)
            .where(cond)
            .order_by(collab_notifications.c.created_at.desc(), collab_notifications.c.notif_id)
            .limit(limit)
        )
        with self.engine.begin() as conn:
            return [self._row_to_notif(r) for r in conn.execute(q).all()]

    def unread_count(self, user_id: str) -> int:
        """Count of unread notifications for the badge."""
        return len(self.list_notifications(user_id, unread_only=True, limit=10_000))

    def mark_read(self, notif_id: str, user_id: str) -> bool:
        """Mark one notification read (scoped to its owner). ``True`` if it existed."""
        with self.engine.begin() as conn:
            res = conn.execute(
                collab_notifications.update()
                .where(
                    and_(
                        collab_notifications.c.notif_id == notif_id,
                        collab_notifications.c.user_id == user_id,
                    )
                )
                .values(read=1)
            )
        return bool(res.rowcount)

    def mark_all_read(self, user_id: str) -> int:
        """Mark all of a user's notifications read; return the number affected."""
        with self.engine.begin() as conn:
            res = conn.execute(
                collab_notifications.update()
                .where(collab_notifications.c.user_id == user_id)
                .values(read=1)
            )
        return int(res.rowcount or 0)

    # -- activity --------------------------------------------------------- #
    def _log_activity(
        self,
        actor: str,
        verb: str,
        target_type: str,
        target_id: str,
        project: str,
        summary: str,
    ) -> Activity:
        rec = Activity(
            activity_id=_new_id("act"),
            actor=actor,
            verb=verb,
            target_type=target_type,
            target_id=target_id,
            project=project,
            summary=summary,
            created_at=_now(),
        )
        with self.engine.begin() as conn:
            conn.execute(
                self._insert(collab_activity).values(
                    activity_id=rec.activity_id,
                    actor=rec.actor,
                    verb=rec.verb,
                    target_type=rec.target_type,
                    target_id=rec.target_id,
                    project=rec.project,
                    summary=rec.summary,
                    created_at=rec.created_at,
                )
            )
        return rec

    def list_activity(self, *, project: str | None = None, limit: int = 100) -> list[Activity]:
        """Recent activity, newest first, optionally scoped to a project/lab."""
        q = select(collab_activity)
        if project:
            q = q.where(collab_activity.c.project == project)
        q = q.order_by(
            collab_activity.c.created_at.desc(), collab_activity.c.activity_id
        ).limit(limit)
        with self.engine.begin() as conn:
            return [self._row_to_activity(r) for r in conn.execute(q).all()]

    # -- comments --------------------------------------------------------- #
    def add_comment(
        self,
        *,
        target_type: str,
        target_id: str,
        author: str,
        body: str,
        parent_id: str = "",
        investigation_id: str = "",
        project: str = "",
    ) -> Comment:
        """Add a comment, extract mentions, fan out notifications, log activity.

        Notification fan-out (§23.32 notification center):

        * every ``@user`` mention → a ``mentioned`` notification;
        * a reply (``parent_id`` set) → a ``reply`` notification to the parent's
          author (unless the same person);
        * a comment inside an investigation → a ``comment`` notification to every
          other member.
        """
        mentions = extract_mentions(body)
        now = _now()
        rec = Comment(
            comment_id=_new_id("cmt"),
            target_type=target_type,
            target_id=target_id,
            author=author,
            body=body,
            status="draft",
            parent_id=parent_id,
            investigation_id=investigation_id,
            project=project,
            mentions=mentions,
            promoted=False,
            created_at=now,
            updated_at=now,
        )
        with self.engine.begin() as conn:
            conn.execute(
                self._insert(collab_comments).values(
                    comment_id=rec.comment_id,
                    target_type=rec.target_type,
                    target_id=rec.target_id,
                    author=rec.author,
                    body=rec.body,
                    status=rec.status,
                    parent_id=rec.parent_id,
                    investigation_id=rec.investigation_id,
                    project=rec.project,
                    mentions_json=json.dumps(mentions, ensure_ascii=False),
                    promoted=0,
                    created_at=now,
                    updated_at=now,
                )
            )
        # fan-out ---------------------------------------------------------
        for handle in mentions:
            if handle.startswith("lab:"):
                continue  # lab mentions are surfaced in activity, not per-user push
            self.notify(
                handle,
                "mentioned",
                f"{author} упомянул(а) вас в комментарии к {target_type} {target_id}",
                actor=author,
                target_type=target_type,
                target_id=target_id,
                investigation_id=investigation_id,
            )
        if parent_id:
            parent = self.get_comment(parent_id)
            if parent is not None and parent.author and parent.author != author:
                self.notify(
                    parent.author,
                    "reply",
                    f"{author} ответил(а) на ваш комментарий "
                    f"к {parent.target_type} {parent.target_id}",
                    actor=author,
                    target_type=target_type,
                    target_id=target_id,
                    investigation_id=investigation_id,
                )
        if investigation_id:
            inv = self.get_investigation(investigation_id)
            if inv is not None:
                for member in {inv.owner, *inv.members}:
                    if member and member != author:
                        self.notify(
                            member,
                            "comment",
                            f"{author} прокомментировал(а) расследование «{inv.title}»",
                            actor=author,
                            target_type=target_type,
                            target_id=target_id,
                            investigation_id=investigation_id,
                        )
        self._log_activity(
            author,
            "commented",
            target_type,
            target_id,
            project,
            f"комментарий к {target_type} {target_id}",
        )
        return rec

    def get_comment(self, comment_id: str) -> Comment | None:
        q = select(collab_comments).where(collab_comments.c.comment_id == comment_id)
        with self.engine.begin() as conn:
            row = conn.execute(q).first()
        return self._row_to_comment(row) if row else None

    def list_comments(
        self, *, target_type: str, target_id: str, include_archived: bool = True
    ) -> list[Comment]:
        """All comments on a target, oldest first (thread order)."""
        cond = and_(
            collab_comments.c.target_type == target_type,
            collab_comments.c.target_id == target_id,
        )
        if not include_archived:
            cond = and_(cond, collab_comments.c.status != "archived")
        q = (
            select(collab_comments)
            .where(cond)
            .order_by(collab_comments.c.created_at, collab_comments.c.comment_id)
        )
        with self.engine.begin() as conn:
            return [self._row_to_comment(r) for r in conn.execute(q).all()]

    def list_comments_for_investigation(self, investigation_id: str) -> list[Comment]:
        q = (
            select(collab_comments)
            .where(collab_comments.c.investigation_id == investigation_id)
            .order_by(collab_comments.c.created_at, collab_comments.c.comment_id)
        )
        with self.engine.begin() as conn:
            return [self._row_to_comment(r) for r in conn.execute(q).all()]

    def set_comment_status(
        self, comment_id: str, status: str, actor: str, *, assignee: str = ""
    ) -> Comment | None:
        """Transition a comment's lifecycle status and dispatch the right notice.

        * ``in_review`` with an ``assignee`` → an ``assigned_review`` notification;
        * ``resolved`` on an ``Evidence`` target → an ``evidence_corrected`` notice
          to the thread participants;
        * ``resolved`` on a ``Gap`` target → a ``gap_closed`` notice.

        ``status`` must be one of :data:`COMMENT_STATUSES`; unknown values raise.
        """
        if status not in COMMENT_STATUSES:
            raise ValueError(f"unknown status {status!r}")
        cur = self.get_comment(comment_id)
        if cur is None:
            return None
        with self.engine.begin() as conn:
            conn.execute(
                collab_comments.update()
                .where(collab_comments.c.comment_id == comment_id)
                .values(status=status, updated_at=_now())
            )
        # dispatch ------------------------------------------------------- #
        if status == "in_review" and assignee:
            self.notify(
                assignee,
                "assigned_review",
                f"{actor} назначил(а) вам ревью комментария к {cur.target_type} {cur.target_id}",
                actor=actor,
                target_type=cur.target_type,
                target_id=cur.target_id,
                investigation_id=cur.investigation_id,
            )
        if status == "resolved":
            recipients = self._thread_participants(cur)
            if cur.target_type.lower() == "evidence":
                for u in recipients:
                    self.notify(
                        u,
                        "evidence_corrected",
                        f"{actor} пометил(а) доказательство {cur.target_id} как исправленное",
                        actor=actor,
                        target_type=cur.target_type,
                        target_id=cur.target_id,
                        investigation_id=cur.investigation_id,
                    )
            elif cur.target_type.lower() == "gap":
                for u in recipients:
                    self.notify(
                        u,
                        "gap_closed",
                        f"{actor} закрыл(а) пробел {cur.target_id}",
                        actor=actor,
                        target_type=cur.target_type,
                        target_id=cur.target_id,
                        investigation_id=cur.investigation_id,
                    )
        self._log_activity(
            actor,
            f"status:{status}",
            cur.target_type,
            cur.target_id,
            cur.project,
            f"статус комментария → {status}",
        )
        return self.get_comment(comment_id)

    def promote_comment(self, comment_id: str, actor: str, promoted: bool = True) -> Comment | None:
        """Manually promote/demote a comment to factual-evidence status (§10.8).

        A comment is *never* treated as factual evidence downstream until this flag
        is set by a human; that is the whole point of keeping comments separate from
        extracted evidence.
        """
        cur = self.get_comment(comment_id)
        if cur is None:
            return None
        with self.engine.begin() as conn:
            conn.execute(
                collab_comments.update()
                .where(collab_comments.c.comment_id == comment_id)
                .values(promoted=1 if promoted else 0, updated_at=_now())
            )
        self._log_activity(
            actor,
            "promoted" if promoted else "demoted",
            cur.target_type,
            cur.target_id,
            cur.project,
            f"комментарий {'повышен до' if promoted else 'снят с'} статуса evidence",
        )
        return self.get_comment(comment_id)

    def _thread_participants(self, comment: Comment) -> set[str]:
        """Everyone who wrote on the same target (+ investigation members), minus none."""
        users = {c.author for c in self.list_comments(
            target_type=comment.target_type, target_id=comment.target_id
        )}
        for handle in comment.mentions:
            if not handle.startswith("lab:"):
                users.add(handle)
        if comment.investigation_id:
            inv = self.get_investigation(comment.investigation_id)
            if inv is not None:
                users.update({inv.owner, *inv.members})
        return {u for u in users if u}

    # -- investigations --------------------------------------------------- #
    def create_investigation(
        self,
        *,
        owner: str,
        title: str,
        notes: str = "",
        project: str = "",
        entities: list[Any] | None = None,
        filters: dict[str, Any] | None = None,
        view: dict[str, Any] | None = None,
        members: list[str] | None = None,
    ) -> Investigation:
        """Create a shared investigation and notify invited members."""
        now = _now()
        members = [m for m in (members or []) if m and m != owner]
        rec = Investigation(
            investigation_id=_new_id("inv"),
            owner=owner,
            title=title,
            notes=notes,
            status="draft",
            project=project,
            entities=entities or [],
            filters=filters or {},
            view=view or {},
            answers=[],
            members=members,
            created_at=now,
            updated_at=now,
        )
        with self.engine.begin() as conn:
            conn.execute(
                self._insert(collab_investigations).values(
                    investigation_id=rec.investigation_id,
                    owner=owner,
                    title=title,
                    notes=notes,
                    status="draft",
                    project=project,
                    entities_json=json.dumps(rec.entities, ensure_ascii=False),
                    filters_json=json.dumps(rec.filters, ensure_ascii=False),
                    view_json=json.dumps(rec.view, ensure_ascii=False),
                    answers_json="[]",
                    members_json=json.dumps(members, ensure_ascii=False),
                    created_at=now,
                    updated_at=now,
                )
            )
        for member in members:
            self.notify(
                member,
                "assigned_review",
                f"{owner} добавил(а) вас в расследование «{title}»",
                actor=owner,
                investigation_id=rec.investigation_id,
            )
        self._log_activity(
            owner,
            "created_investigation",
            "Investigation",
            rec.investigation_id,
            project,
            f"создано расследование «{title}»",
        )
        return rec

    def get_investigation(self, investigation_id: str) -> Investigation | None:
        q = select(collab_investigations).where(
            collab_investigations.c.investigation_id == investigation_id
        )
        with self.engine.begin() as conn:
            row = conn.execute(q).first()
        return self._row_to_investigation(row) if row else None

    def list_investigations(self, user_id: str | None = None) -> list[Investigation]:
        """List investigations visible to ``user_id`` (owner or member); all if None."""
        q = select(collab_investigations).order_by(
            collab_investigations.c.updated_at.desc(),
            collab_investigations.c.investigation_id,
        )
        with self.engine.begin() as conn:
            rows = [self._row_to_investigation(r) for r in conn.execute(q).all()]
        if user_id is None:
            return rows
        return [r for r in rows if r.owner == user_id or user_id in r.members]

    def update_investigation(
        self,
        investigation_id: str,
        actor: str,
        *,
        title: str | None = None,
        notes: str | None = None,
        status: str | None = None,
        entities: list[Any] | None = None,
        filters: dict[str, Any] | None = None,
        view: dict[str, Any] | None = None,
        members: list[str] | None = None,
        append_answer: dict[str, Any] | None = None,
    ) -> Investigation | None:
        """Patch an investigation; only provided fields change. Returns the new state.

        ``append_answer`` pushes one entry onto the answer-history log (a saved
        Q&A from the graph), which is the "answer history" part of the workspace.
        ``status`` must be one of :data:`INVESTIGATION_STATUSES`.
        """
        cur = self.get_investigation(investigation_id)
        if cur is None:
            return None
        if status is not None and status not in INVESTIGATION_STATUSES:
            raise ValueError(f"unknown status {status!r}")
        values: dict[str, Any] = {"updated_at": _now()}
        if title is not None:
            values["title"] = title
        if notes is not None:
            values["notes"] = notes
        if status is not None:
            values["status"] = status
        if entities is not None:
            values["entities_json"] = json.dumps(entities, ensure_ascii=False)
        if filters is not None:
            values["filters_json"] = json.dumps(filters, ensure_ascii=False)
        if view is not None:
            values["view_json"] = json.dumps(view, ensure_ascii=False)
        new_members = cur.members
        if members is not None:
            new_members = [m for m in members if m and m != cur.owner]
            values["members_json"] = json.dumps(new_members, ensure_ascii=False)
        if append_answer is not None:
            answers = [*cur.answers, {**append_answer, "at": _now()}]
            values["answers_json"] = json.dumps(answers, ensure_ascii=False)
        with self.engine.begin() as conn:
            conn.execute(
                collab_investigations.update()
                .where(collab_investigations.c.investigation_id == investigation_id)
                .values(**values)
            )
        # notify newly-added members
        if members is not None:
            for member in set(new_members) - set(cur.members):
                self.notify(
                    member,
                    "assigned_review",
                    f"{actor} добавил(а) вас в расследование «{cur.title}»",
                    actor=actor,
                    investigation_id=investigation_id,
                )
        if status is not None and status != cur.status:
            self._log_activity(
                actor,
                f"investigation:{status}",
                "Investigation",
                investigation_id,
                cur.project,
                f"статус расследования → {status}",
            )
        elif append_answer is not None:
            self._log_activity(
                actor,
                "saved_answer",
                "Investigation",
                investigation_id,
                cur.project,
                "сохранён ответ в историю расследования",
            )
        return self.get_investigation(investigation_id)

    # -- row mappers ------------------------------------------------------ #
    @staticmethod
    def _row_to_comment(row: Any) -> Comment:
        m = row._mapping
        return Comment(
            comment_id=m["comment_id"],
            target_type=m["target_type"],
            target_id=m["target_id"],
            author=m["author"],
            body=m["body"],
            status=m["status"],
            parent_id=m["parent_id"],
            investigation_id=m["investigation_id"],
            project=m["project"],
            mentions=json.loads(m["mentions_json"] or "[]"),
            promoted=bool(m["promoted"]),
            created_at=m["created_at"],
            updated_at=m["updated_at"],
        )

    @staticmethod
    def _row_to_investigation(row: Any) -> Investigation:
        m = row._mapping
        return Investigation(
            investigation_id=m["investigation_id"],
            owner=m["owner"],
            title=m["title"],
            notes=m["notes"],
            status=m["status"],
            project=m["project"],
            entities=json.loads(m["entities_json"] or "[]"),
            filters=json.loads(m["filters_json"] or "{}"),
            view=json.loads(m["view_json"] or "{}"),
            answers=json.loads(m["answers_json"] or "[]"),
            members=json.loads(m["members_json"] or "[]"),
            created_at=m["created_at"],
            updated_at=m["updated_at"],
        )

    @staticmethod
    def _row_to_notif(row: Any) -> Notification:
        m = row._mapping
        return Notification(
            notif_id=m["notif_id"],
            user_id=m["user_id"],
            kind=m["kind"],
            text=m["text"],
            actor=m["actor"],
            target_type=m["target_type"],
            target_id=m["target_id"],
            investigation_id=m["investigation_id"],
            read=bool(m["read"]),
            created_at=m["created_at"],
        )

    @staticmethod
    def _row_to_activity(row: Any) -> Activity:
        m = row._mapping
        return Activity(
            activity_id=m["activity_id"],
            actor=m["actor"],
            verb=m["verb"],
            target_type=m["target_type"],
            target_id=m["target_id"],
            project=m["project"],
            summary=m["summary"],
            created_at=m["created_at"],
        )
