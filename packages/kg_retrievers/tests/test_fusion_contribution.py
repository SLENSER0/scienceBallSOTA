"""Hand-checkable tests for §12.4 per-source contribution attribution.

Проверяем вклады/доли/доминанту фьюзинга и сортировку :func:`attribute_many`.
"""

from __future__ import annotations

from kg_retrievers.fusion_contribution import (
    ContributionBreakdown,
    attribute,
    attribute_many,
)


def test_total_is_weighted_sum() -> None:
    """(1) total == сумма components*weights == 1.0."""
    b = attribute("d", {"dense": 1.0, "sparse": 1.0}, {"dense": 0.75, "sparse": 0.25})
    assert b.total == 1.0


def test_contributions_are_component_times_weight() -> None:
    """(2) contributions == {dense: 0.75, sparse: 0.25}."""
    b = attribute("d", {"dense": 1.0, "sparse": 1.0}, {"dense": 0.75, "sparse": 0.25})
    assert b.contributions == {"dense": 0.75, "sparse": 0.25}


def test_shares_normalize_to_contributions() -> None:
    """(3) shares == {dense: 0.75, sparse: 0.25} (total == 1.0)."""
    b = attribute("d", {"dense": 1.0, "sparse": 1.0}, {"dense": 0.75, "sparse": 0.25})
    assert b.shares == {"dense": 0.75, "sparse": 0.25}


def test_dominant_is_largest_contribution() -> None:
    """(4) dominant == 'dense' (0.75 > 0.25)."""
    b = attribute("d", {"dense": 1.0, "sparse": 1.0}, {"dense": 0.75, "sparse": 0.25})
    assert b.dominant == "dense"


def test_ties_break_by_name_ascending() -> None:
    """(5) равные вклады → dominant — лексикографически меньшее имя."""
    b = attribute("d", {"dense": 1.0, "sparse": 1.0}, {"dense": 0.5, "sparse": 0.5})
    assert b.contributions == {"dense": 0.5, "sparse": 0.5}
    assert b.dominant == "dense"  # 'dense' < 'sparse'

    # Проверяем сам механизм ничьей независимо от порядка вставки.
    b2 = attribute("d", {"zeta": 1.0, "alpha": 1.0}, {"zeta": 0.4, "alpha": 0.4})
    assert b2.dominant == "alpha"


def test_zero_total_gives_zero_shares_no_div_by_zero() -> None:
    """(6) total == 0 → все shares 0.0, без ZeroDivisionError."""
    b = attribute("d", {"dense": 1.0, "sparse": 2.0}, {"dense": 0.0, "sparse": 0.0})
    assert b.total == 0.0
    assert b.shares == {"dense": 0.0, "sparse": 0.0}
    # dominant всё ещё определён (все вклады равны 0 → меньшее имя).
    assert b.dominant == "dense"


def test_source_absent_from_weights_contributes_zero() -> None:
    """(7) источник без веса вносит 0.0."""
    b = attribute("d", {"dense": 1.0, "bm25": 5.0}, {"dense": 1.0})
    assert b.contributions == {"dense": 1.0, "bm25": 0.0}
    assert b.total == 1.0
    assert b.dominant == "dense"


def test_attribute_many_sorts_by_total_desc() -> None:
    """(8) attribute_many ставит документ с большим total первым."""
    weights = {"dense": 1.0, "sparse": 1.0}
    rows = {
        "low": {"dense": 0.1, "sparse": 0.1},
        "high": {"dense": 0.9, "sparse": 0.8},
        "mid": {"dense": 0.5, "sparse": 0.4},
    }
    out = attribute_many(rows, weights)
    assert [b.doc_id for b in out] == ["high", "mid", "low"]
    assert out[0].total > out[1].total > out[2].total


def test_attribute_many_tie_breaks_by_doc_id() -> None:
    """attribute_many: равные total → сортировка по doc_id возрастанию."""
    weights = {"dense": 1.0}
    rows = {"beta": {"dense": 1.0}, "alpha": {"dense": 1.0}}
    out = attribute_many(rows, weights)
    assert [b.doc_id for b in out] == ["alpha", "beta"]


def test_as_dict_shares_sum_to_one() -> None:
    """(9) as_dict()['shares'] суммируется в ~1.0 при total > 0."""
    b = attribute(
        "d",
        {"dense": 0.6, "sparse": 0.3, "bm25": 0.1},
        {"dense": 1.0, "sparse": 1.0, "bm25": 1.0},
    )
    d = b.as_dict()
    assert abs(sum(d["shares"].values()) - 1.0) < 1e-9
    assert d["doc_id"] == "d"
    assert d["dominant"] == "dense"
    assert set(d) == {"doc_id", "total", "contributions", "shares", "dominant"}


def test_empty_components_dominant_is_empty() -> None:
    """Пустые components → total 0.0, dominant пуст, без ошибок."""
    b = attribute("d", {}, {"dense": 1.0})
    assert b.total == 0.0
    assert b.contributions == {}
    assert b.shares == {}
    assert b.dominant == ""


def test_frozen_dataclass_is_immutable() -> None:
    """ContributionBreakdown заморожен (frozen dataclass)."""
    import dataclasses

    b = attribute("d", {"dense": 1.0}, {"dense": 1.0})
    assert isinstance(b, ContributionBreakdown)
    try:
        b.total = 2.0  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected FrozenInstanceError")
