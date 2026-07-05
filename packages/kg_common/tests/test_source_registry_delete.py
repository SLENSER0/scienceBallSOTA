"""Source registry destructive delete — тесты (§3, §5.4).

Covers :meth:`SourceRegistry.delete`: register→delete→gone, idempotent absent
delete returns ``False``, and deleting one source leaves the others intact.
"""

from __future__ import annotations

import pytest

from kg_common.storage.source_registry import Source, SourceRegistry


@pytest.fixture
def reg() -> SourceRegistry:
    r = SourceRegistry("sqlite:///:memory:")
    r.migrate()
    return r


def test_register_then_delete_removes_row(reg: SourceRegistry) -> None:
    """After deleting a registered source ``get`` returns ``None`` and delete → ``True``."""
    reg.register(Source("src:1", title="Отчёт", sha256="h1"))
    assert reg.get("src:1") is not None
    assert reg.delete("src:1") is True
    assert reg.get("src:1") is None


def test_delete_absent_returns_false(reg: SourceRegistry) -> None:
    """Deleting a non-existent source is idempotent — returns ``False``, not an error."""
    assert reg.delete("nope") is False
    # And a second delete of an already-removed source is also a no-op ``False``.
    reg.register(Source("src:1", sha256="h1"))
    assert reg.delete("src:1") is True
    assert reg.delete("src:1") is False


def test_delete_leaves_other_sources_intact(reg: SourceRegistry) -> None:
    """Delete targets only the exact ``source_id`` — siblings survive untouched."""
    reg.register(Source("src:1", title="one", sha256="h1"))
    reg.register(Source("src:2", title="two", sha256="h2"))
    reg.register(Source("src:3", title="three", sha256="h3"))

    assert reg.delete("src:2") is True

    remaining = {s.source_id for s in reg.list()}
    assert remaining == {"src:1", "src:3"}
    assert reg.get("src:1") is not None and reg.get("src:1").title == "one"
    assert reg.get("src:3") is not None and reg.get("src:3").title == "three"
    # The freed content hash no longer resolves.
    assert reg.exists("h2") is False
    assert reg.exists("h1") is True
