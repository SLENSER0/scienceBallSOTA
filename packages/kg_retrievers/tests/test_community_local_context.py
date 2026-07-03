"""Tests for the GraphRAG local-search context builder (§11.7).

Проверяем фиксированный порядок секций, сортировку по score внутри секции,
соблюдение бюджета токенов, подсчёт dropped и детерминизм. Hand-checkable:
token cost of a text is ``len(text) // chars_per_token`` (default 4).
"""

from __future__ import annotations

from kg_retrievers.community_local_context import (
    SECTION_ORDER,
    LocalContext,
    build_local_context,
)


def _big_budget() -> int:
    """A budget large enough that nothing is dropped in the sample fixtures."""
    return 1000


def test_fixed_section_order() -> None:
    """The four sections appear in the fixed §11.7 order regardless of inputs."""
    ctx = build_local_context(
        reports=[("r1", "report one", 1.0)],
        entities=[("e1", "entity one", 1.0)],
        relationships=[("rel1", "relationship one", 1.0)],
        text_units=[("t1", "source one", 1.0)],
        budget_tokens=_big_budget(),
    )
    names = [name for name, _lines in ctx.sections]
    assert names == ["reports", "entities", "relationships", "sources"]
    assert names == list(SECTION_ORDER)
    # 'sources' section is last.
    assert ctx.sections[-1][0] == "sources"


def test_entities_sorted_by_score_desc() -> None:
    """Within 'entities' a score-3 item precedes a score-1 item."""
    ctx = build_local_context(
        reports=[],
        entities=[("low", "low-score entity", 1.0), ("high", "high-score entity", 3.0)],
        relationships=[],
        text_units=[],
        budget_tokens=_big_budget(),
    )
    entities_section = dict(ctx.sections)["entities"]
    assert entities_section == ("high-score entity", "low-score entity")
    assert entities_section.index("high-score entity") < entities_section.index("low-score entity")


def test_used_tokens_within_budget_and_dropped_counted() -> None:
    """Items exceeding the budget are excluded and counted in dropped."""
    # Each text is 40 chars -> 10 tokens at chars_per_token=4. Budget 25 => 2 fit.
    text = "x" * 40
    ctx = build_local_context(
        reports=[
            ("r1", text, 3.0),
            ("r2", text, 2.0),
            ("r3", text, 1.0),
        ],
        entities=[],
        relationships=[],
        text_units=[],
        budget_tokens=25,
    )
    reports_lines = dict(ctx.sections)["reports"]
    assert len(reports_lines) == 2  # 10 + 10 <= 25; third (would be 30) drops
    assert ctx.used_tokens == 20
    assert ctx.used_tokens <= 25
    assert ctx.dropped == 1


def test_all_empty_inputs() -> None:
    """All-empty inputs give used_tokens==0 and dropped==0, sections still present."""
    ctx = build_local_context(
        reports=[],
        entities=[],
        relationships=[],
        text_units=[],
        budget_tokens=100,
    )
    assert ctx.used_tokens == 0
    assert ctx.dropped == 0
    assert [name for name, _l in ctx.sections] == list(SECTION_ORDER)
    assert all(lines == () for _name, lines in ctx.sections)


def test_deterministic_equal() -> None:
    """Two identical calls are equal (frozen dataclass value equality)."""
    kwargs = {
        "reports": [("r1", "aaaa aaaa aaaa", 2.0)],
        "entities": [("e1", "bbbb", 1.0), ("e2", "cccc cccc", 3.0)],
        "relationships": [("x", "dddd dddd", 1.5)],
        "text_units": [("t", "eeee", 0.5)],
        "budget_tokens": 50,
    }
    a = build_local_context(**kwargs)
    b = build_local_context(**kwargs)
    assert a == b
    assert isinstance(a, LocalContext)


def test_as_dict_shape() -> None:
    """as_dict()['sections'][0]['name']=='reports' and lines serialise as a list."""
    ctx = build_local_context(
        reports=[("r1", "hello report", 1.0)],
        entities=[],
        relationships=[],
        text_units=[("t1", "a source", 1.0)],
        budget_tokens=_big_budget(),
    )
    d = ctx.as_dict()
    assert d["sections"][0]["name"] == "reports"
    assert d["sections"][0]["lines"] == ["hello report"]
    assert d["sections"][-1]["name"] == "sources"
    assert isinstance(d["sections"][0]["lines"], list)
    assert d["used_tokens"] == ctx.used_tokens
    assert d["dropped"] == ctx.dropped


def test_dropped_from_later_section_still_packs_earlier() -> None:
    """A too-big item in one section drops but a fitting item elsewhere is kept."""
    small = "y" * 4  # 1 token
    huge = "z" * 400  # 100 tokens, never fits budget 10
    ctx = build_local_context(
        reports=[("r", huge, 5.0)],
        entities=[("e", small, 5.0)],
        relationships=[],
        text_units=[],
        budget_tokens=10,
    )
    sections = dict(ctx.sections)
    assert sections["reports"] == ()  # huge dropped
    assert sections["entities"] == (small,)  # small kept
    assert ctx.used_tokens == 1
    assert ctx.dropped == 1
