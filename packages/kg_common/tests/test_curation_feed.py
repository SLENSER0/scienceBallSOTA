"""Curation activity feed (§16.9): лента курирующих событий (activity feed)."""

from __future__ import annotations

import pytest

from kg_common.storage.curation_feed import CurationFeed, FeedEntry


@pytest.fixture
def feed() -> CurationFeed:
    f = CurationFeed("sqlite:///:memory:")
    f.migrate()
    return f


def test_record_and_recent_newest_first(feed: CurationFeed) -> None:
    feed.record("e1", "alice", "merge", "ent:1", "merged A", "2026-07-01T00:00:00")
    feed.record("e2", "bob", "correct", "ent:2", "fixed B", "2026-07-02T00:00:00")
    feed.record("e3", "alice", "revert", "ent:1", "reverted", "2026-07-03T00:00:00")
    rows = feed.recent()
    # newest-first: e3 (Jul 3) -> e2 (Jul 2) -> e1 (Jul 1)
    assert [r.event_id for r in rows] == ["e3", "e2", "e1"]
    assert rows[0].actor == "alice" and rows[0].summary == "reverted"


def test_recent_filter_by_actor(feed: CurationFeed) -> None:
    feed.record("e1", "alice", "merge", "ent:1", "s1", "2026-07-01T00:00:00")
    feed.record("e2", "bob", "merge", "ent:2", "s2", "2026-07-02T00:00:00")
    feed.record("e3", "alice", "split", "ent:3", "s3", "2026-07-03T00:00:00")
    rows = feed.recent(actor="alice")
    assert [r.event_id for r in rows] == ["e3", "e1"]
    assert all(r.actor == "alice" for r in rows)


def test_recent_filter_by_action(feed: CurationFeed) -> None:
    feed.record("e1", "alice", "merge", "ent:1", "s1", "2026-07-01T00:00:00")
    feed.record("e2", "bob", "revert", "ent:2", "s2", "2026-07-02T00:00:00")
    feed.record("e3", "carol", "merge", "ent:3", "s3", "2026-07-03T00:00:00")
    rows = feed.recent(action="merge")
    assert [r.event_id for r in rows] == ["e3", "e1"]
    assert all(r.action == "merge" for r in rows)


def test_recent_limit_truncates_newest(feed: CurationFeed) -> None:
    for i in range(5):
        feed.record(f"e{i}", "alice", "merge", "ent:1", f"s{i}", f"2026-07-0{i + 1}T00:00:00")
    rows = feed.recent(limit=2)
    # only the two newest survive (e4 = Jul 5, e3 = Jul 4)
    assert [r.event_id for r in rows] == ["e4", "e3"]
    assert len(rows) == 2


def test_record_is_idempotent_upsert_by_event_id(feed: CurationFeed) -> None:
    feed.record("e1", "alice", "merge", "ent:1", "first", "2026-07-01T00:00:00")
    # re-record same event_id: no duplicate row, fields updated (latest wins)
    feed.record("e1", "bob", "revert", "ent:9", "second", "2026-07-05T00:00:00")
    assert feed.count() == 1
    rows = feed.recent()
    assert len(rows) == 1
    entry = rows[0]
    assert entry.event_id == "e1" and entry.actor == "bob"
    assert entry.action == "revert" and entry.target_id == "ent:9"
    assert entry.summary == "second" and entry.created_at == "2026-07-05T00:00:00"


def test_count_reflects_distinct_events(feed: CurationFeed) -> None:
    assert feed.count() == 0
    feed.record("e1", "alice", "merge", "ent:1", "s1", "2026-07-01T00:00:00")
    feed.record("e2", "bob", "merge", "ent:2", "s2", "2026-07-02T00:00:00")
    assert feed.count() == 2
    # re-recording an existing id does not grow the count
    feed.record("e1", "alice", "merge", "ent:1", "s1b", "2026-07-03T00:00:00")
    assert feed.count() == 2


def test_empty_feed_is_graceful(feed: CurationFeed) -> None:
    assert feed.recent() == []
    assert feed.recent(actor="nobody", action="merge") == []
    assert feed.count() == 0


def test_record_returns_entry_and_as_dict_exposes_all_fields(feed: CurationFeed) -> None:
    returned = feed.record("e1", "alice", "merge", "ent:1", "did a thing", "2026-07-01T00:00:00")
    assert isinstance(returned, FeedEntry)
    data = returned.as_dict()
    assert data == {
        "event_id": "e1",
        "actor": "alice",
        "action": "merge",
        "target_id": "ent:1",
        "summary": "did a thing",
        "created_at": "2026-07-01T00:00:00",
    }
