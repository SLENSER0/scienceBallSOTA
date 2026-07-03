"""Tests for the Cmd+K command palette index (§17.5).

Проверяют сборку записей из четырёх источников, camelCase-сериализацию,
скоринг совпадений (префикс/начало слова/подстрока), исключение записей без
совпадений, регистронезависимость и предельное число результатов.

Cover building entries from the four sources, camelCase serialisation, match
scoring (prefix/word-start/substring), dropping non-matches, case-insensitive
matching and the result limit.
"""

from __future__ import annotations

from api_gateway.command_palette_index import (
    PaletteEntry,
    build_palette,
    rank_palette,
)


def _entry(label: str, *, keywords: tuple[str, ...] = (), eid: str = "x") -> PaletteEntry:
    """Небольшая фабрика тестовых записей. Small factory for test entries."""
    return PaletteEntry(
        id=eid,
        kind="entity",
        label=label,
        subtitle="",
        route=f"/entity/{eid}",
        keywords=keywords,
        score=0.0,
    )


def test_as_dict_camel_case_and_keywords_list() -> None:
    entry = PaletteEntry(
        id="e1",
        kind="entity",
        label="Al",
        subtitle="Material",
        route="/entity/e1",
        keywords=("al",),
        score=3.0,
    )
    assert entry.as_dict() == {
        "id": "e1",
        "kind": "entity",
        "label": "Al",
        "subtitle": "Material",
        "route": "/entity/e1",
        "keywords": ["al"],
        "score": 3.0,
    }


def test_build_palette_kinds_routes_and_lowercase_keywords() -> None:
    palette = build_palette(
        entities=[{"id": "e1", "label": "Al-Cu alloy", "keywords": ["AL", "Cu"]}],
        saved_views=[{"id": "v1", "label": "My view"}],
        recent_questions=[{"id": "q1", "label": "What is Al?"}],
        routes=[{"id": "graph", "label": "Graph", "route": "/graph"}],
    )
    kinds = [e.kind for e in palette]
    assert kinds == ["entity", "saved_view", "question", "route"]
    assert palette[0].route == "/entity/e1"
    assert palette[0].keywords == ("al", "cu")  # lower-cased
    assert palette[1].route == "/views/v1"
    assert palette[2].route == "/chat/q1"
    assert palette[3].route == "/graph"  # explicit route wins


def test_rank_orders_prefix_over_word_start_over_substring() -> None:
    entries = (
        _entry("metal (Al)", eid="a"),  # substring 1.0
        _entry("Peak-aged Al", eid="b"),  # word-start 2.0
        _entry("Al-Cu alloy", eid="c"),  # prefix 3.0
    )
    ranked = rank_palette(entries, "Al")
    assert [e.label for e in ranked] == ["Al-Cu alloy", "Peak-aged Al", "metal (Al)"]
    assert [e.score for e in ranked] == [3.0, 2.0, 1.0]


def test_empty_query_returns_first_limit_in_input_order() -> None:
    entries = tuple(_entry(f"L{i}", eid=str(i)) for i in range(5))
    ranked = rank_palette(entries, "", limit=3)
    assert [e.label for e in ranked] == ["L0", "L1", "L2"]
    # Whitespace-only is treated as empty too.
    assert rank_palette(entries, "   ", limit=2) == entries[:2]


def test_query_is_case_insensitive() -> None:
    ranked = rank_palette((_entry("alloy"),), "ALLOY")
    assert len(ranked) == 1
    assert ranked[0].score == 3.0


def test_keyword_only_match_is_included() -> None:
    entry = _entry("Widget", keywords=("foobar",), eid="w")
    ranked = rank_palette((entry,), "foo")
    assert len(ranked) == 1
    assert ranked[0].id == "w"
    assert ranked[0].score == 3.0  # keyword prefix match


def test_non_matching_entry_is_dropped() -> None:
    entries = (_entry("alpha", eid="a"), _entry("zzz", eid="z"))
    ranked = rank_palette(entries, "alp")
    assert [e.id for e in ranked] == ["a"]


def test_limit_caps_result_count() -> None:
    entries = tuple(_entry("alloy", eid=str(i)) for i in range(6))
    ranked = rank_palette(entries, "al", limit=2)
    assert len(ranked) == 2


def test_stable_tie_break_keeps_input_order() -> None:
    entries = (
        _entry("Alpha", eid="1"),
        _entry("Alto", eid="2"),
        _entry("Almond", eid="3"),
    )
    ranked = rank_palette(entries, "al")  # all prefix 3.0
    assert [e.id for e in ranked] == ["1", "2", "3"]
