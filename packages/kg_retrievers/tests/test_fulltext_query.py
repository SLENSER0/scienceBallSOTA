"""Tests for :mod:`kg_retrievers.fulltext_query` (§3.12 Lucene query builder).

Hand-checkable assertions on escaping and query assembly; no store handles are needed
because the module only builds the query string (Kuzu note §3: custom props are read
via ``get_node``, not here).
"""

from __future__ import annotations

from kg_retrievers.fulltext_query import (
    DEFAULT_INDEX,
    FulltextQuery,
    build_alias_query,
    build_entity_query,
    escape_lucene,
)

# -- escape_lucene ----------------------------------------------------------------


def test_escape_plain_alphanumeric_unchanged() -> None:
    assert escape_lucene("AA2024") == "AA2024"


def test_escape_colon() -> None:
    assert escape_lucene("a:b") == "a\\:b"


def test_escape_dash_and_parens() -> None:
    out = escape_lucene("Al-Cu (2024)")
    # '-', '(' and ')' each gain a leading backslash; letters/digits/space stay.
    assert out == "Al\\-Cu \\(2024\\)"
    assert "\\-" in out
    assert "\\(" in out
    assert "\\)" in out


def test_escape_every_special_gets_a_backslash() -> None:
    for ch in '+-!(){}[]^"~*?:\\/&|':
        assert escape_lucene(ch) == "\\" + ch


def test_escape_slash() -> None:
    assert escape_lucene("mg/l") == "mg\\/l"


# -- build_entity_query -----------------------------------------------------------


def test_entity_query_or_joins_tokens() -> None:
    assert build_entity_query("Al Cu").lucene == "Al OR Cu"


def test_entity_query_single_token() -> None:
    q = build_entity_query("AA2024")
    assert q.lucene == "AA2024"
    assert q.raw == "AA2024"


def test_entity_query_fuzzy_appends_tilde_one() -> None:
    assert build_entity_query("AA2024", fuzzy=True).lucene == "AA2024~1"


def test_entity_query_fuzzy_multi_token() -> None:
    assert build_entity_query("Al Cu", fuzzy=True).lucene == "Al~1 OR Cu~1"


def test_entity_query_escapes_tokens() -> None:
    # 'Al-Cu' is one whitespace token -> escaped whole, no OR split.
    assert build_entity_query("Al-Cu").lucene == "Al\\-Cu"


def test_entity_query_empty_is_empty() -> None:
    q = build_entity_query("")
    assert q.lucene == ""
    assert q.raw == ""


def test_entity_query_whitespace_only_is_empty() -> None:
    assert build_entity_query("   ").lucene == ""


def test_entity_query_as_dict_default_index() -> None:
    assert build_entity_query("x").as_dict()["index"] == "entity_name_index"


def test_entity_query_custom_index() -> None:
    q = build_entity_query("x", index="other_index")
    assert q.index == "other_index"
    assert q.as_dict() == {"index": "other_index", "raw": "x", "lucene": "x"}


# -- build_alias_query ------------------------------------------------------------


def test_alias_query_or_joins_and_escapes() -> None:
    lucene = build_alias_query(["AA2024", "Al-Cu 2024"]).lucene
    assert " OR " in lucene
    assert "\\-" in lucene
    assert lucene == "AA2024 OR Al\\-Cu 2024"


def test_alias_query_raw_preserves_unescaped_join() -> None:
    q = build_alias_query(["AA2024", "Al-Cu 2024"])
    assert q.raw == "AA2024 OR Al-Cu 2024"


def test_alias_query_skips_blank_aliases() -> None:
    # A blank alias must not create a dangling ' OR '.
    assert build_alias_query(["AA2024", "", "  "]).lucene == "AA2024"


def test_alias_query_default_index() -> None:
    assert build_alias_query(["x"]).index == DEFAULT_INDEX


# -- FulltextQuery dataclass ------------------------------------------------------


def test_fulltext_query_is_frozen() -> None:
    import dataclasses

    q = FulltextQuery(index="i", raw="r", lucene="l")
    try:
        q.index = "z"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - guard
        raise AssertionError("FulltextQuery must be frozen")


def test_fulltext_query_as_dict_roundtrip() -> None:
    q = FulltextQuery(index="i", raw="r", lucene="l")
    assert q.as_dict() == {"index": "i", "raw": "r", "lucene": "l"}
