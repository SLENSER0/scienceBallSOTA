"""Saved views + user settings store (§14.15)."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

from kg_common.storage.saved_views import SavedView, ViewStore


@pytest.fixture
def store() -> ViewStore:
    s = ViewStore("sqlite:///:memory:")
    s.migrate()
    return s


def test_save_and_get_view_roundtrips_payload(store: ViewStore) -> None:
    payload = {
        "filters": {"domain": "физика", "confidence": 0.8},
        "columns": ["name", "value"],
        "sort": [{"col": "value", "dir": "desc"}],
    }
    saved = store.save_view("v:1", "u:1", "Мой вид", "graph", payload)
    assert isinstance(saved, SavedView)
    got = store.get_view("v:1")
    assert got is not None
    assert got.view_id == "v:1"
    assert got.user_id == "u:1"
    assert got.name == "Мой вид"
    assert got.kind == "graph"
    assert got.created_at != ""  # timestamp stamped on save
    # payload round-trips through JSON as a structured dict (nested + unicode)
    assert got.payload == payload
    assert got.as_dict()["payload"]["filters"]["domain"] == "физика"


def test_get_missing_view_returns_none(store: ViewStore) -> None:
    assert store.get_view("nope") is None


def test_list_views_by_user(store: ViewStore) -> None:
    store.save_view("v1", "alice", "A", "table", {"a": 1})
    store.save_view("v2", "alice", "B", "graph", {"b": 2})
    store.save_view("v3", "bob", "C", "table", {"c": 3})
    alice = store.list_views("alice")
    assert {v.view_id for v in alice} == {"v1", "v2"}
    assert all(isinstance(v, SavedView) for v in alice)
    assert store.list_views("bob") == store.list_views("bob")  # deterministic
    assert {v.view_id for v in store.list_views("bob")} == {"v3"}


def test_delete_view(store: ViewStore) -> None:
    store.save_view("v1", "u", "A", "table", {"a": 1})
    store.save_view("v2", "u", "B", "table", {"b": 2})
    assert len(store.list_views("u")) == 2
    store.delete_view("v1")
    assert store.get_view("v1") is None
    assert {v.view_id for v in store.list_views("u")} == {"v2"}
    store.delete_view("does-not-exist")  # no-op, graceful


def test_save_view_is_idempotent_upsert(store: ViewStore) -> None:
    first = store.save_view("v", "u", "old", "table", {"n": 1})
    updated = store.save_view("v", "u", "new", "graph", {"n": 2})  # UPSERT by PK
    assert len(store.list_views("u")) == 1  # no duplicate row
    assert updated.name == "new"
    assert updated.kind == "graph"
    assert updated.payload == {"n": 2}
    assert updated.created_at == first.created_at  # created_at preserved


def test_settings_set_and_get(store: ViewStore) -> None:
    settings = {"theme": "dark", "lang": "ru", "page_size": 50}
    returned = store.set_settings("u:1", settings)
    assert returned == settings
    assert store.get_settings("u:1") == settings


def test_set_settings_replaces_not_merges(store: ViewStore) -> None:
    store.set_settings("u", {"theme": "dark", "lang": "ru"})
    store.set_settings("u", {"lang": "en"})  # replace drops "theme"
    assert store.get_settings("u") == {"lang": "en"}


def test_update_settings_merges_keys(store: ViewStore) -> None:
    store.set_settings("u", {"theme": "dark", "lang": "ru"})
    merged = store.update_settings("u", {"lang": "en", "page_size": 25})
    # existing "theme" preserved, "lang" overwritten, "page_size" added
    assert merged == {"theme": "dark", "lang": "en", "page_size": 25}
    assert store.get_settings("u") == merged


def test_update_settings_on_empty_starts_from_scratch(store: ViewStore) -> None:
    # update on a user with no prior settings behaves like set (graceful)
    merged = store.update_settings("fresh", {"a": 1})
    assert merged == {"a": 1}
    assert store.get_settings("fresh") == {"a": 1}


def test_empty_graceful(store: ViewStore) -> None:
    assert store.list_views("nobody") == []
    assert store.get_settings("nobody") == {}
    assert store.get_view("nobody") is None


# -- performance: user_id index for list_views (sqlite-index optimization) ------
def test_user_index_created_by_migrate(store: ViewStore) -> None:
    """migrate() must create the composite (user_id, created_at) list_views index."""
    indexes = inspect(store.engine).get_indexes("saved_views")
    by_name = {ix["name"]: ix for ix in indexes}
    assert "ix_saved_views_user" in by_name, f"missing index; have {list(by_name)}"
    # composite: seeks WHERE user_id=? and serves the ORDER BY created_at key
    assert by_name["ix_saved_views_user"]["column_names"] == ["user_id", "created_at"]


def test_index_is_behavior_preserving_for_list_views(store: ViewStore) -> None:
    """Adding the index changes access path only — same rows, same order out."""
    store.save_view("v1", "alice", "A", "table", {"a": 1})
    store.save_view("v2", "alice", "B", "graph", {"b": 2})
    store.save_view("v3", "bob", "C", "table", {"c": 3})
    alice = store.list_views("alice")
    # WHERE user_id still isolates the user; ORDER BY (created_at, view_id) still holds
    assert {v.view_id for v in alice} == {"v1", "v2"}
    assert [v.view_id for v in alice] == sorted(
        (v.view_id for v in alice),
        key=lambda vid: ({v.view_id: v.created_at for v in alice}[vid], vid),
    )
    assert all(isinstance(v, SavedView) for v in alice)
    assert store.list_views("alice") == store.list_views("alice")  # deterministic
