"""§2 store-factory selects the backend by runtime profile."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from kg_retrievers.store_factory import make_graph_store


@dataclass
class _Secret:
    value: str

    def get_secret_value(self) -> str:
        return self.value


@dataclass
class _FakeSettings:
    runtime_profile: str
    kuzu_db_path: str = "/tmp/does-not-matter"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: _Secret = None  # type: ignore[assignment]


def test_embedded_profile_returns_kuzu(tmp_path):
    s = _FakeSettings(runtime_profile="embedded", kuzu_db_path=str(tmp_path / "g"))
    store = make_graph_store(s)
    assert type(store).__name__ == "KuzuGraphStore"
    store.close()


def test_server_profile_returns_neo4j():
    s = _FakeSettings(runtime_profile="server", neo4j_password=_Secret("password"))
    try:
        store = make_graph_store(s)
    except Exception as exc:
        pytest.skip(f"neo4j unreachable: {type(exc).__name__}")
    assert type(store).__name__ == "Neo4jGraphStore"
    store.close()
