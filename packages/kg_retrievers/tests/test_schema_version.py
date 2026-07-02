"""Schema version guard (§3.15)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.schema_version import (
    CURRENT_VERSION,
    apply_schema_version,
    check_schema_or_raise,
    migrate_status,
    schema_checksum,
)


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def test_apply_and_status(store: KuzuGraphStore) -> None:
    st = apply_schema_version(store)
    assert st.current == CURRENT_VERSION and st.up_to_date
    assert migrate_status(store).checksum == schema_checksum()


def test_guard_bootstraps_when_absent(store: KuzuGraphStore) -> None:
    # first-run guard records the version instead of failing
    check_schema_or_raise(store)
    assert migrate_status(store).current == CURRENT_VERSION


def test_guard_raises_on_mismatch(store: KuzuGraphStore) -> None:
    apply_schema_version(store, version="0.0.1")
    with pytest.raises(RuntimeError, match="schema version mismatch"):
        check_schema_or_raise(store, expected=CURRENT_VERSION)
