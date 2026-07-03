"""Mention → entity linking against an alias map (§6.19)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_extractors.entity_linking import (
    ALIAS_SCORE,
    EXACT_SCORE,
    FUZZY_THRESHOLD,
    EntityLink,
    link_all,
    link_mention,
)

# Two entities sharing the "Fe…" prefix so exact/alias/fuzzy stay separable.
_ALIAS_MAP: dict[str, dict[str, object]] = {
    "entity:iron": {"canonical": "Iron", "aliases": ["Fe", "ferrum"]},
    "entity:hematite": {"canonical": "Hematite", "aliases": ["Fe2O3", "red ochre"]},
}


def test_constants_are_pinned() -> None:
    # Hand-checkable scoring contract (§6.19).
    assert EXACT_SCORE == 1.0
    assert ALIAS_SCORE == 0.95
    assert FUZZY_THRESHOLD == 85.0


def test_exact_canonical_link_score_one() -> None:
    link = link_mention("Iron", _ALIAS_MAP)
    assert link is not None
    assert link.entity_id == "entity:iron"
    assert link.method == "exact"
    assert link.score == 1.0
    assert link.surface == "Iron"


def test_alias_link() -> None:
    link = link_mention("ferrum", _ALIAS_MAP)
    assert link is not None
    assert link.entity_id == "entity:iron"
    assert link.method == "alias"
    assert link.score == 0.95
    # A formula-like alias resolves to its own entity, not the "Fe" one.
    other = link_mention("Fe2O3", _ALIAS_MAP)
    assert other is not None
    assert other.entity_id == "entity:hematite"
    assert other.method == "alias"


def test_fuzzy_near_miss() -> None:
    # "Hematit" is "Hematite" minus its final letter: rapidfuzz ratio 93.33.
    link = link_mention("Hematit", _ALIAS_MAP)
    assert link is not None
    assert link.entity_id == "entity:hematite"
    assert link.method == "fuzzy"
    assert link.score == pytest.approx(14 / 15)  # 93.333.../100
    assert FUZZY_THRESHOLD / 100.0 <= link.score < 1.0


def test_no_match_returns_none() -> None:
    # Best fuzzy candidate ("hematite") scores 28.57 — well below threshold.
    assert link_mention("quartz", _ALIAS_MAP) is None
    assert link_mention("   ", _ALIAS_MAP) is None
    assert link_mention("", _ALIAS_MAP) is None


def test_method_recorded() -> None:
    methods = {
        link_mention("Iron", _ALIAS_MAP).method,  # type: ignore[union-attr]
        link_mention("Fe", _ALIAS_MAP).method,  # type: ignore[union-attr]
        link_mention("Hematit", _ALIAS_MAP).method,  # type: ignore[union-attr]
    }
    assert methods == {"exact", "alias", "fuzzy"}


def test_as_dict_full_shape() -> None:
    link = link_mention("Fe", _ALIAS_MAP)
    assert link is not None
    assert link.as_dict() == {
        "surface": "Fe",
        "entity_id": "entity:iron",
        "score": 0.95,
        "method": "alias",
    }


def test_link_all_maps_a_list() -> None:
    result = link_all(["Iron", "quartz", "Fe"], _ALIAS_MAP)
    assert len(result) == 3  # positional 1:1 mapping, misses kept as None
    assert result[0] == EntityLink("Iron", "entity:iron", 1.0, "exact")
    assert result[1] is None
    assert result[2] == EntityLink("Fe", "entity:iron", 0.95, "alias")


def test_empty_alias_map_returns_none() -> None:
    assert link_mention("Iron", {}) is None
    assert link_all(["Iron", "Fe"], {}) == [None, None]


def test_case_insensitive() -> None:
    # Canonical and alias both fold case; internal/edge whitespace is collapsed.
    upper = link_mention("IRON", _ALIAS_MAP)
    assert upper is not None
    assert upper.entity_id == "entity:iron"
    assert upper.method == "exact"
    assert upper.score == 1.0
    lower_alias = link_mention("  red    OCHRE ", _ALIAS_MAP)
    assert lower_alias is not None
    assert lower_alias.entity_id == "entity:hematite"
    assert lower_alias.method == "alias"


def test_entity_link_is_frozen() -> None:
    link = EntityLink("Iron", "entity:iron", 1.0, "exact")
    with pytest.raises(FrozenInstanceError):
        link.entity_id = "entity:hematite"  # type: ignore[misc]
