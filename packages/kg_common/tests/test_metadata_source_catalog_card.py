"""Tests for §10.7 source-catalog card assembler — карточка каталога источников.

RU: Проверяет сборку карточки, группировку по лабораториям и AND-фильтрацию.
EN: Covers card assembly, lab grouping, and AND-semantics filtering.
"""

from __future__ import annotations

from kg_common.metadata.source_catalog_card import (
    SourceCatalogCard,
    build_card,
    cards_by_lab,
    filter_cards,
)


def _sample_cards() -> list[SourceCatalogCard]:
    """RU: Три карточки для фильтров/группировки. EN: Three cards for filter/group tests."""
    return [
        build_card(
            {"source_id": "a", "owner": "u", "lab": "l1", "access_policy": "internal"},
            freshness="fresh",
        ),
        build_card(
            {"source_id": "b", "owner": "u", "lab": "l1", "access_policy": "public"},
            freshness="aging",
        ),
        build_card(
            {"source_id": "c", "owner": "v", "lab": "l2", "access_policy": "internal"},
            freshness="stale",
        ),
    ]


def test_build_card_counts_and_access() -> None:
    """RU: Счётчики и access из access_policy. EN: Counts kept, access from access_policy."""
    card = build_card(
        {"source_id": "s", "owner": "u", "lab": "l1", "access_policy": "internal", "version": 2},
        freshness="fresh",
        evidence_count=3,
    )
    assert card.evidence_count == 3
    assert card.run_count == 0
    assert card.version == 2
    assert card.access == "internal"


def test_build_card_missing_owner_is_empty() -> None:
    """RU: Отсутствующий owner → ''. EN: A source missing owner yields owner==''."""
    card = build_card({"source_id": "s", "lab": "l1"}, freshness="fresh")
    assert card.owner == ""
    assert card.name == ""
    assert card.access == ""
    assert card.version == 1


def test_as_dict_roundtrip() -> None:
    """RU: as_dict содержит freshness. EN: as_dict()['freshness'] reflects the level."""
    card = build_card(
        {"source_id": "s", "owner": "u", "lab": "l1", "access_policy": "internal"},
        freshness="fresh",
    )
    data = card.as_dict()
    assert data["freshness"] == "fresh"
    assert data["source_id"] == "s"
    assert set(data) == {
        "source_id",
        "name",
        "owner",
        "lab",
        "access",
        "version",
        "freshness",
        "evidence_count",
        "run_count",
        "last_ingest",
    }


def test_filter_cards_by_lab() -> None:
    """RU: Фильтр по лаборатории. EN: filter_cards(lab='l1') returns only l1 cards."""
    result = filter_cards(_sample_cards(), lab="l1")
    assert [c.source_id for c in result] == ["a", "b"]


def test_filter_cards_and_semantics() -> None:
    """RU: owner И access вместе. EN: filter_cards(owner='u', access='internal') ANDs both."""
    result = filter_cards(_sample_cards(), owner="u", access="internal")
    assert [c.source_id for c in result] == ["a"]


def test_filter_cards_no_criteria_returns_all() -> None:
    """RU: Без критериев — все карточки. EN: filter_cards(cards) returns all cards."""
    cards = _sample_cards()
    assert filter_cards(cards) == cards


def test_cards_by_lab_groups() -> None:
    """RU: Две карточки l1 под ключом 'l1'. EN: two l1 cards group under key 'l1'."""
    grouped = cards_by_lab(_sample_cards())
    assert set(grouped) == {"l1", "l2"}
    assert len(grouped["l1"]) == 2
    assert [c.source_id for c in grouped["l1"]] == ["a", "b"]
    assert len(grouped["l2"]) == 1


def test_none_value_falls_back_to_empty() -> None:
    """RU: Явный None → ''. EN: An explicit None owner also falls back to ''."""
    card = build_card({"source_id": "s", "owner": None, "lab": "l1"}, freshness="fresh")
    assert card.owner == ""
