"""Live per-doctype OpenSearch index tests (§4.6).

These run against the **live** cluster on ``localhost:9200`` (security disabled).
Every index is namespaced with a deterministic per-process prefix ``t_idx_<pid>_``
(PID token, no ``random``) so parallel processes never collide, and the module
teardown drops each one. If the cluster is genuinely unreachable the whole module
skips — it never runs red offline.

The pure-data assertions (spec coverage, distinctive fields) need no cluster; the
live assertions create the four prefixed indices, read back their ``_mapping`` and
confirm each doctype's distinctive fields landed, then drop them.
"""

from __future__ import annotations

import os

import pytest
from opensearchpy.exceptions import OpenSearchException

from kg_retrievers.opensearch_indices import (
    INDEX_SPECS,
    IndexSpec,
    drop_indices,
    ensure_indices,
)
from kg_retrievers.opensearch_store import OpenSearchKeywordStore

# Deterministic per-process namespace (PID token, no `random`) (§4.6).
_PREFIX = f"t_idx_{os.getpid()}_"
_EXPECTED = {"kg_chunks", "kg_table_rows", "kg_claims", "kg_entities"}
_NAMES = [f"{_PREFIX}{name}" for name in INDEX_SPECS]


@pytest.fixture(scope="module")
def client():  # type: ignore[no-untyped-def]
    """A live client with a clean throwaway namespace; skips if OpenSearch is down (§4.6)."""
    try:
        store = OpenSearchKeywordStore()
        if not store.ping():
            pytest.skip("live OpenSearch unreachable on localhost:9200")
    except OpenSearchException as exc:  # pragma: no cover - offline path
        pytest.skip(f"live OpenSearch unreachable: {exc}")
    except Exception as exc:  # pragma: no cover - connection refused etc.
        pytest.skip(f"live OpenSearch unreachable: {exc}")
    conn = store.client
    drop_indices(conn, _NAMES)  # clean slate in case a prior run crashed mid-way
    try:
        yield conn
    finally:
        drop_indices(conn, _NAMES)  # always clean up our test namespace


def _mapping_props(conn, index: str) -> dict:  # type: ignore[no-untyped-def]
    """The live ``mappings.properties`` block of ``index`` (§4.6)."""
    resp = conn.indices.get_mapping(index=index)
    return resp[index]["mappings"]["properties"]


def test_index_specs_cover_all_four_doctypes() -> None:
    """INDEX_SPECS has exactly the four doctype indices, each a real builder (§4.6)."""
    assert set(INDEX_SPECS) == _EXPECTED
    for name, spec in INDEX_SPECS.items():
        assert isinstance(spec, IndexSpec)
        assert spec.name == name
        body = spec.as_dict()
        # every doctype carries the base scientific_text analyzer + a properties map.
        assert "scientific_text" in body["settings"]["analysis"]["analyzer"]
        assert "text" in body["mappings"]["properties"]  # base body field


def test_variant_mappings_declare_distinctive_fields() -> None:
    """Each variant adds exactly its doctype fields; base stays free of extras (§4.6)."""
    rows = INDEX_SPECS["kg_table_rows"].as_dict()["mappings"]["properties"]
    assert rows["table_id"]["type"] == "keyword"
    assert rows["row_index"]["type"] == "integer"
    assert rows["col_index"]["type"] == "integer"

    claims = INDEX_SPECS["kg_claims"].as_dict()["mappings"]["properties"]
    assert claims["claim_type"]["type"] == "keyword"
    assert claims["subject_id"]["type"] == "keyword"

    entities = INDEX_SPECS["kg_entities"].as_dict()["mappings"]["properties"]
    assert entities["entity_type"]["type"] == "keyword"
    assert entities["aliases_text"]["type"] == "text"
    assert entities["aliases_text"]["analyzer"] == "scientific_text"

    # kg_chunks is the plain base body — no doctype extras leak into it.
    chunks = INDEX_SPECS["kg_chunks"].as_dict()["mappings"]["properties"]
    assert not ({"table_id", "row_index", "claim_type", "entity_type"} & set(chunks))


def test_as_dict_is_independent_per_call() -> None:
    """Building a spec twice yields equal but independent dicts (idempotent) (§4.6)."""
    spec = INDEX_SPECS["kg_table_rows"]
    first, second = spec.as_dict(), spec.as_dict()
    assert first == second and first is not second
    first["mappings"]["properties"]["table_id"] = {"type": "text"}
    assert second["mappings"]["properties"]["table_id"] == {"type": "keyword"}


def test_ensure_indices_is_idempotent_on_live_cluster(client) -> None:  # type: ignore[no-untyped-def]
    """First call creates all four prefixed indices; second is an all-False no-op (§4.6)."""
    created = ensure_indices(client, prefix=_PREFIX)
    assert set(created) == set(_NAMES)
    assert all(created.values())  # every index freshly created
    for name in _NAMES:
        assert client.indices.exists(index=name) is True

    again = ensure_indices(client, prefix=_PREFIX)
    assert again == dict.fromkeys(_NAMES, False)  # nothing re-created


def test_live_mappings_contain_distinctive_fields(client) -> None:  # type: ignore[no-untyped-def]
    """Each live index's server-side mapping carries its doctype fields (§4.6)."""
    ensure_indices(client, prefix=_PREFIX)

    rows = _mapping_props(client, f"{_PREFIX}kg_table_rows")
    assert "table_id" in rows and "row_index" in rows
    assert rows["row_index"]["type"] == "integer"

    claims = _mapping_props(client, f"{_PREFIX}kg_claims")
    assert claims["claim_type"]["type"] == "keyword"

    entities = _mapping_props(client, f"{_PREFIX}kg_entities")
    assert entities["entity_type"]["type"] == "keyword"


def test_drop_indices_removes_the_namespace(client) -> None:  # type: ignore[no-untyped-def]
    """drop_indices deletes every index and is safe to repeat (ignores 404) (§4.6)."""
    ensure_indices(client, prefix=_PREFIX)
    for name in _NAMES:
        assert client.indices.exists(index=name) is True

    drop_indices(client, _NAMES)
    for name in _NAMES:
        assert client.indices.exists(index=name) is False

    drop_indices(client, _NAMES)  # dropping absent indices is a no-op (404 ignored)
