"""Tests for the OpenSearch mapping + pure-python analyzer (§4.6).

Every expected token list is hand-derivable: NFKC + lowercase, keep maximal runs
of RU/EN letters or digits, drop anything shorter than two characters. The mapping
assertions read the create-index body OpenSearch would receive.
"""

from __future__ import annotations

import dataclasses

import pytest

from kg_retrievers.keyword_schema import (
    KEYWORD_FIELDS,
    NUMERIC_FIELDS,
    SCIENTIFIC_ANALYZER,
    TEXT_FIELDS,
    analyze,
    build_index_mapping,
)


def test_analyze_lowercases_and_keeps_250() -> None:
    """Case-folds EN text and keeps the numeric token ``250`` intact (§4.6)."""
    assert analyze("Al2O3 250 MPa") == ["al2o3", "250", "mpa"]
    # Purely numeric multi-digit runs survive as their own token.
    assert "250" in analyze("Hardness measured at 250 degrees")


def test_analyze_keeps_russian_tokens() -> None:
    """RU text lower-cases and yields Cyrillic tokens alongside numbers (§4.6)."""
    assert analyze("Прочность Стали 250") == ["прочность", "стали", "250"]
    # ``ё`` folds and is kept (it is outside the а-я run but handled explicitly).
    assert analyze("Плёнка") == ["плёнка"]


def test_analyze_drops_punctuation() -> None:
    """Punctuation delimits tokens and never appears inside one (§4.6)."""
    assert analyze("hardness, corrosion!") == ["hardness", "corrosion"]
    # A hyphen splits chemical shorthand into its parts.
    assert analyze("Al-Cu") == ["al", "cu"]


def test_analyze_drops_short_tokens() -> None:
    """Single-character stray tokens (RU/EN, digits) fall below MIN_TOKEN_LEN (§4.6)."""
    assert analyze("a al 5 250") == ["al", "250"]
    assert analyze("я и он") == ["он"]  # 1-char RU dropped, 2-char kept


def test_analyze_empty_returns_empty() -> None:
    """Empty and punctuation-only input fold to no tokens (§4.6)."""
    assert analyze("") == []
    assert analyze("   ") == []
    assert analyze("!!! --- ,.") == []


def test_analyze_keeps_alnum_tokens_whole() -> None:
    """Contiguous letter+digit runs (units/chemicals) stay a single token (§4.6)."""
    assert analyze("AA2024 sample") == ["aa2024", "sample"]


def test_mapping_declares_scientific_analyzer() -> None:
    """The mapping's analysis settings define the ``scientific_text`` analyzer (§4.6)."""
    analyzers = build_index_mapping()["settings"]["analysis"]["analyzer"]
    assert SCIENTIFIC_ANALYZER.name == "scientific_text"
    assert "scientific_text" in analyzers
    body = analyzers["scientific_text"]
    assert body["type"] == "custom"
    assert body["tokenizer"] == SCIENTIFIC_ANALYZER.tokenizer
    assert "lowercase" in body["filter"]  # matches analyze()'s case-folding


def test_mapping_text_fields_use_analyzer() -> None:
    """Every text field is ``type: text`` bound to the scientific analyzer (§4.6)."""
    props = build_index_mapping()["mappings"]["properties"]
    for field in TEXT_FIELDS:
        assert field in ("name", "aliases_text", "text")
        assert props[field]["type"] == "text"
        assert props[field]["analyzer"] == "scientific_text"


def test_mapping_keyword_vs_text_fields() -> None:
    """Keyword facet fields are unanalyzed keywords, distinct from text fields (§4.6)."""
    props = build_index_mapping()["mappings"]["properties"]
    # §4.6 facet fields: ids + domain + material/property/source_type/review_status.
    assert {"material_ids", "property_ids", "source_type", "review_status"} <= set(KEYWORD_FIELDS)
    for field in KEYWORD_FIELDS:
        assert props[field] == {"type": "keyword"}
        assert "analyzer" not in props[field]
    # A text field is never a keyword and vice-versa.
    assert props["name"]["type"] == "text"
    assert props["id"]["type"] == "keyword"


def test_mapping_numeric_field() -> None:
    """Numeric range-filter fields are ``float`` incl. the §4.6 measurand fields."""
    props = build_index_mapping()["mappings"]["properties"]
    assert {"value_normalized", "temperature_c", "time_h", "confidence"} <= set(NUMERIC_FIELDS)
    for field in NUMERIC_FIELDS:
        assert props[field] == {"type": "float"}
    assert props["published_date"] == {"type": "date"}


def test_mapping_is_idempotent_and_analyzer_frozen() -> None:
    """Rebuilding yields equal independent dicts; the descriptor is frozen (§4.6)."""
    first, second = build_index_mapping(), build_index_mapping()
    assert first == second
    assert first is not second  # independent objects, safe to mutate a copy
    with pytest.raises(dataclasses.FrozenInstanceError):
        SCIENTIFIC_ANALYZER.name = "other"  # type: ignore[misc]
