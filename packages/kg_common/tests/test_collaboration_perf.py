"""Behavior-preserving performance guards for CollaborationStore (§23.32).

Covers two optimizations that must not change results:

* the four secondary indexes on the hot read filters exist after ``migrate()``
  (index seek instead of full table scan);
* ``unread_count`` returns the SQL ``COUNT(*)`` — identical to the old
  ``len(list_notifications(..., unread_only=True))`` — without materialising rows.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

from kg_common.storage.collaboration import CollaborationStore


@pytest.fixture
def store() -> CollaborationStore:
    s = CollaborationStore("sqlite:///:memory:")
    s.migrate()
    return s


def test_hot_read_indexes_created(store: CollaborationStore) -> None:
    """migrate() creates the four indexes on the non-PK filter columns."""
    insp = inspect(store.engine)

    def index_map(table: str) -> dict[str, list[str]]:
        return {ix["name"]: list(ix["column_names"]) for ix in insp.get_indexes(table)}

    comments = index_map("collab_comments")
    assert comments["ix_collab_comments_target"] == ["target_type", "target_id"]
    assert comments["ix_collab_comments_investigation"] == ["investigation_id"]

    notifs = index_map("collab_notifications")
    assert notifs["ix_collab_notifications_user"] == ["user_id"]

    activity = index_map("collab_activity")
    assert activity["ix_collab_activity_project"] == ["project"]


def _unread_via_list(store: CollaborationStore, user_id: str) -> int:
    """The old implementation: materialise unread rows and len() them."""
    return len(store.list_notifications(user_id, unread_only=True, limit=10_000))


def test_unread_count_matches_old_list_len(store: CollaborationStore) -> None:
    """COUNT(*) == len(list_notifications(unread_only=True)) across every scenario."""
    # two unread for alice, one for bob (actor != recipient so they persist)
    n1 = store.notify("alice", "mentioned", "t1", actor="bob")
    store.notify("alice", "reply", "t2", actor="carol")
    store.notify("bob", "comment", "t3", actor="alice")

    assert store.unread_count("alice") == _unread_via_list(store, "alice") == 2
    assert store.unread_count("bob") == _unread_via_list(store, "bob") == 1
    assert store.unread_count("nobody") == _unread_via_list(store, "nobody") == 0

    # marking one read drops the count by one, still matches the list-len oracle
    store.mark_read(n1.notif_id, "alice")
    assert store.unread_count("alice") == _unread_via_list(store, "alice") == 1
    # total notifications unchanged — only the read flag moved
    assert len(store.list_notifications("alice")) == 2

    # mark_all_read zeroes the badge for that user only
    store.mark_all_read("alice")
    assert store.unread_count("alice") == _unread_via_list(store, "alice") == 0
    assert store.unread_count("bob") == 1


def test_unread_count_skips_self_and_empty_recipients(store: CollaborationStore) -> None:
    """Self-notifications / empty recipients are never persisted, so never counted."""
    store.notify("alice", "mentioned", "self", actor="alice")  # self -> skipped
    store.notify("", "mentioned", "empty", actor="bob")  # empty user -> skipped
    assert store.unread_count("alice") == _unread_via_list(store, "alice") == 0
