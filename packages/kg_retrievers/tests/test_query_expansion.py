"""Query expansion via synonyms / aliases (§12.13, pure python).

Hand-checkable tests over a tiny fixed alias_map (canonical -> list[alias], RU|EN): the
reverse-osmosis (обратный осмос) synonym group is the anchor, so every add is a single
unambiguous target. No store, no network — pure python.
"""

from __future__ import annotations

from kg_retrievers.query_expansion import ExpandedQuery, expand_query

# canonical -> aliases (§12.13). Folding is case-/punctuation-insensitive.
ALIASES = {
    "reverse osmosis": ["обратный осмос", "ро"],
    "polymer membrane": ["полимерная мембрана"],
}


def test_canonical_mention_adds_aliases() -> None:
    # §12.13: a query mentioning the canonical term pulls in its aliases.
    exp = expand_query("reverse osmosis is cheap", ALIASES)
    assert exp.added == ("обратный осмос", "ро")
    # Original terms are kept, aliases appended after them.
    assert exp.terms == ("reverse", "osmosis", "is", "cheap", "обратный осмос", "ро")


def test_alias_mention_adds_canonical() -> None:
    # §12.13: an alias in the query pulls in the canonical (and sibling aliases).
    exp = expand_query("ро works well", ALIASES)
    assert exp.added == ("reverse osmosis", "обратный осмос")
    assert "reverse osmosis" in exp.terms


def test_alias_mention_case_and_punct_folded() -> None:
    # Folding (canonical_key) is case-/punctuation-insensitive: 'Reverse-Osmosis' matches.
    exp = expand_query("Reverse-Osmosis pilot", ALIASES)
    assert exp.added == ("обратный осмос", "ро")


def test_unknown_terms_unchanged() -> None:
    # A query with no recognized mention is returned verbatim (nothing added).
    exp = expand_query("quantum cryptography", ALIASES)
    assert exp.added == ()
    assert exp.terms == ("quantum", "cryptography")


def test_dedup_present_surfaces_not_re_added() -> None:
    # 'ро' and 'reverse osmosis' are both literally present -> only the missing sibling
    # ('обратный осмос') is added, and no term is duplicated.
    exp = expand_query("ро reverse osmosis", ALIASES)
    assert exp.added == ("обратный осмос",)
    assert exp.terms == ("ро", "reverse", "osmosis", "обратный осмос")
    assert len(exp.terms) == len(set(exp.terms))


def test_dedup_repeated_original_terms() -> None:
    # Repeated query tokens collapse to one (first occurrence kept).
    exp = expand_query("ро ро good", ALIASES)
    assert exp.terms == ("ро", "good", "reverse osmosis", "обратный осмос")


def test_original_preserved_first() -> None:
    # The original query terms always lead; the original string is echoed on the dataclass.
    exp = expand_query("ро pilot", ALIASES)
    assert exp.original == "ро pilot"
    assert exp.terms[:2] == ("ро", "pilot")


def test_empty_alias_map_returns_original_only() -> None:
    # No aliases known -> just the (de-duplicated) original terms, nothing added.
    exp = expand_query("reverse osmosis", {})
    assert exp.added == ()
    assert exp.terms == ("reverse", "osmosis")
    assert exp.original == "reverse osmosis"


def test_empty_query() -> None:
    # An empty query yields empty terms and no additions.
    exp = expand_query("", ALIASES)
    assert exp.terms == ()
    assert exp.added == ()
    assert exp.original == ""


def test_multiple_groups_expand() -> None:
    # Two distinct mentions each expand, in alias_map iteration order.
    exp = expand_query("reverse osmosis polymer membrane", ALIASES)
    assert exp.added == ("обратный осмос", "ро", "полимерная мембрана")


def test_as_dict_shape() -> None:
    exp = expand_query("ро pilot", ALIASES)
    d = exp.as_dict()
    assert d == {
        "original": "ро pilot",
        "terms": ["ро", "pilot", "reverse osmosis", "обратный осмос"],
        "added": ["reverse osmosis", "обратный осмос"],
    }
    assert isinstance(d["terms"], list)
    assert isinstance(d["added"], list)


def test_frozen_immutable() -> None:
    exp = expand_query("ро", ALIASES)
    assert isinstance(exp, ExpandedQuery)
    try:
        exp.terms = ()  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject assignment
        raise AssertionError("ExpandedQuery must be frozen")
