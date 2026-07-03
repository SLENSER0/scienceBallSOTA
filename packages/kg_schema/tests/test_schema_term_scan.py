"""Тесты детекции ``new_schema_term`` — сканирование неизвестных терминов (§16.5)."""

from __future__ import annotations

from kg_schema.schema_term_scan import (
    UnknownTermFinding,
    _normalize,
    nearest_known,
    scan_terms,
)


def test_case_insensitive_hit_yields_no_finding() -> None:
    """(1) 'Hardness' при словаре ['hardness'] — находок нет (регистр игнорируется)."""
    observed = [{"term": "Hardness", "kind": "property", "context": "steel bar"}]
    assert scan_terms(observed, ["hardness"]) == []


def test_unknown_term_yields_one_finding_with_kind() -> None:
    """(2) 'nanoindentation' вне словаря — одна находка, вид (kind) перенесён."""
    observed = [{"term": "nanoindentation", "kind": "method", "context": "AFM tip"}]
    findings = scan_terms(observed, ["hardness"])
    assert len(findings) == 1
    assert findings[0].term == "nanoindentation"
    assert findings[0].kind == "method"
    # Без близкого термина подсказки нет.
    assert findings[0].suggested_mapping is None


def test_suggested_mapping_by_prefix_near_match() -> None:
    """(3) 'hardnes' почти совпадает по префиксу — suggested_mapping='hardness'."""
    observed = [{"term": "hardnes", "kind": "property", "context": "typo in table"}]
    findings = scan_terms(observed, ["hardness"])
    assert len(findings) == 1
    assert findings[0].suggested_mapping == "hardness"


def test_dedup_same_normalized_term_and_kind() -> None:
    """(4) Два наблюдения одного нормализованного term+kind — одна находка (первый context)."""
    observed = [
        {"term": "Nanoindentation", "kind": "method", "context": "first mention"},
        {"term": "  nanoindentation ", "kind": "method", "context": "second mention"},
    ]
    findings = scan_terms(observed, ["hardness"])
    assert len(findings) == 1
    assert findings[0].context == "first mention"


def test_as_dict_target_type_is_schema() -> None:
    """(5) as_dict()['target_type'] == 'schema'."""
    finding = UnknownTermFinding(
        term="creep rate",
        kind="property",
        context="high-temperature test",
        suggested_mapping=None,
    )
    payload = finding.as_dict()
    assert payload["target_type"] == "schema"
    assert payload["term"] == "creep rate"
    assert payload["suggested_mapping"] is None


def test_empty_observed_returns_empty_list() -> None:
    """(6) Пустой ``observed`` -> []."""
    assert scan_terms([], ["hardness", "yield strength"]) == []


def test_whitespace_variant_matches_vocabulary_entry() -> None:
    """(7) '  Yield  Strength ' совпадает с записью словаря 'yield strength'."""
    observed = [{"term": "  Yield  Strength ", "kind": "property", "context": "tensile"}]
    assert scan_terms(observed, ["yield strength"]) == []


def test_normalize_collapses_whitespace_and_lowercases() -> None:
    """Прямая проверка :func:`_normalize` — регистр, обрезка, схлопывание пробелов."""
    assert _normalize("  Yield  Strength ") == "yield strength"
    assert _normalize("Hardness") == "hardness"
    assert _normalize("a\t\nb") == "a b"


def test_nearest_known_returns_none_without_match() -> None:
    """:func:`nearest_known` -> None, если ни одна запись словаря не близка."""
    assert nearest_known("nanoindentation", ["hardness"]) is None
    assert nearest_known("", ["hardness"]) is None


def test_nearest_known_prefers_smallest_length_delta() -> None:
    """:func:`nearest_known` выбирает кандидата с наименьшей разницей длин."""
    # 'hard' — префикс обоих; ближе по длине 'hardness', чем 'hardness modulus'.
    assert nearest_known("hard", ["hardness modulus", "hardness"]) == "hardness"
