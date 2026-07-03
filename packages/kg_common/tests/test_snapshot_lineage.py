"""Tests for snapshot lineage & restore-point selection (§16.10).

Ручные, проверяемые тесты: линейная цепочка из 3 снапшотов, разрыв по
отсутствующему `parent_id`, выбор точки восстановления по времени (между,
до, точное совпадение), корень без пометки broken и форма as_dict().
"""

from __future__ import annotations

from kg_common.storage.snapshot_lineage import (
    SnapshotChain,
    build_chain,
    restore_point,
)


def _snap(sid: str, parent: str | None, created: str) -> dict[str, object]:
    """Мини-фабрика снапшота: id/parent_id/created_at."""
    return {"id": sid, "parent_id": parent, "created_at": created}


# Линейная цепочка s1 <- s2 <- s3 (s1 — корень, s3 — голова).
S1 = _snap("s1", None, "2026-01-01T00:00:00Z")
S2 = _snap("s2", "s1", "2026-02-01T00:00:00Z")
S3 = _snap("s3", "s2", "2026-03-01T00:00:00Z")


def test_linear_chain_order_and_head() -> None:
    """(1) 3-снапшотная линейная цепочка → order длины 3, head == новейший."""
    chain = build_chain([S1, S2, S3])
    assert chain.head == "s3"
    assert len(chain.order) == 3
    assert chain.order == ["s3", "s2", "s1"]
    assert chain.broken == []


def test_missing_parent_marked_broken() -> None:
    """(2) parent_id на отсутствующий id → снапшот попадает в broken."""
    orphan = _snap("s3", "missing-99", "2026-03-01T00:00:00Z")
    chain = build_chain([S1, S2, orphan])
    assert "s3" in chain.broken
    # Разрыв: голова s3 не дотягивается до корня через отсутствующий parent.
    assert chain.head == "s3"
    assert chain.order == ["s3"]


def test_restore_point_between_returns_earlier() -> None:
    """(3) restore_point между s2 и s3 возвращает id s2."""
    at = "2026-02-15T00:00:00Z"
    assert restore_point([S1, S2, S3], at) == "s2"


def test_restore_point_before_oldest_none() -> None:
    """(4) restore_point раньше самого старого → None."""
    at = "2025-12-31T23:59:59Z"
    assert restore_point([S1, S2, S3], at) is None


def test_restore_point_exact_match_inclusive() -> None:
    """(5) restore_point ровно на created_at снапшота возвращает этот снапшот."""
    assert restore_point([S1, S2, S3], S2["created_at"]) == "s2"


def test_root_terminates_chain_not_broken() -> None:
    """(6) корневой снапшот (parent_id None) завершает цепочку, не помечен broken."""
    chain = build_chain([S1, S2, S3])
    assert "s1" in chain.order
    assert "s1" not in chain.broken
    assert chain.broken == []


def test_as_dict_order_is_list() -> None:
    """(7) as_dict()['order'] — это list."""
    chain = build_chain([S1, S2, S3])
    d = chain.as_dict()
    assert isinstance(d, dict)
    assert isinstance(d["order"], list)
    assert d["head"] == "s3"
    assert isinstance(d["broken"], list)


def test_empty_input_yields_empty_chain() -> None:
    """Пустой вход → пустая цепочка (граничный случай)."""
    chain = build_chain([])
    assert chain == SnapshotChain(head="", order=[], broken=[])
