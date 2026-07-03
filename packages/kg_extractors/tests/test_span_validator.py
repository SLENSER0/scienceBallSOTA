"""Evidence-span validator tests — «no span → no fact» (§6.10).

Hand-checked expectations over RU + EN text; verifies exact offsets, fuzzy
whitespace/case normalization (Cyrillic), not-found rejection, offset-mismatch
flagging, first-occurrence semantics, empty spans, and aggregate counts.
"""

from __future__ import annotations

from kg_extractors.span_validator import (
    STATUS_EXACT,
    STATUS_NORMALIZED,
    STATUS_NOT_FOUND,
    STATUS_OFFSET_MISMATCH,
    ExtractionReport,
    SpanValidation,
    find_span,
    validate_extraction,
    validate_span,
)


def test_exact_substring_found_with_correct_offsets() -> None:
    source = "Yield strength was 350 MPa at room temperature."
    span = "350 MPa"
    v = validate_span(source, span)
    assert v.status == STATUS_EXACT
    assert (v.char_start, v.char_end) == (19, 26)
    assert source[v.char_start : v.char_end] == span
    assert v.matched_text == span
    assert v.ok is True
    assert v.fuzzy_used is False


def test_find_span_exact_offsets() -> None:
    source = "The sample Fe-18Cr-8Ni was annealed."
    assert find_span(source, "Fe-18Cr-8Ni") == (11, 22)
    assert source[11:22] == "Fe-18Cr-8Ni"


def test_leading_trailing_whitespace_normalized_match() -> None:
    # span carries extra padding the source lacks -> not exact, but normalized.
    source = "Сталь Fe-18Cr прочна при нагреве."
    span = "  Fe-18Cr  "
    v = validate_span(source, span)
    assert v.status == STATUS_NORMALIZED
    assert v.fuzzy_used is True
    assert v.matched_text == "Fe-18Cr"
    assert source[v.char_start : v.char_end] == "Fe-18Cr"
    assert (v.char_start, v.char_end) == (6, 13)


def test_internal_whitespace_collapsed_to_normalized() -> None:
    source = "The yield strength value is high."
    span = "yield   strength"  # multiple internal spaces vs single in source
    v = validate_span(source, span)
    assert v.status == STATUS_NORMALIZED
    assert v.matched_text == "yield strength"
    assert source[v.char_start : v.char_end] == "yield strength"


def test_case_insensitive_cyrillic_normalized() -> None:
    source = "Раствор медный купорос синего цвета."
    span = "МЕДНЫЙ КУПОРОС"
    v = validate_span(source, span)
    assert v.status == STATUS_NORMALIZED
    assert v.matched_text == "медный купорос"
    assert source[v.char_start : v.char_end] == "медный купорос"
    assert v.ok is True


def test_hallucinated_span_not_found() -> None:
    source = "Твёрдость по Виккерсу составила 220 HV."
    v = validate_span(source, "предел текучести 500 МПа")
    assert v.status == STATUS_NOT_FOUND
    assert v.char_start is None and v.char_end is None
    assert v.matched_text is None
    assert v.ok is False


def test_fuzzy_disabled_rejects_case_mismatch() -> None:
    source = "Раствор медный купорос."
    v = validate_span(source, "МЕДНЫЙ", fuzzy=False)
    assert v.status == STATUS_NOT_FOUND


def test_provided_offsets_confirmed_exact() -> None:
    source = "Yield strength was 350 MPa."
    v = validate_span(source, "350 MPa", char_start=19, char_end=26)
    assert v.status == STATUS_EXACT
    assert (v.char_start, v.char_end) == (19, 26)


def test_provided_offsets_disagree_offset_mismatch() -> None:
    source = "The value is 42 units in total."
    # caller claims offsets 0..2 ("Th"), which do not contain "42".
    v = validate_span(source, "42", char_start=0, char_end=2)
    assert v.status == STATUS_OFFSET_MISMATCH
    assert (v.char_start, v.char_end) == (0, 2)
    assert v.matched_text == "Th"
    assert v.ok is False


def test_multiple_occurrences_returns_first() -> None:
    source = "MPa here and MPa there and MPa again."
    assert find_span(source, "MPa") == (0, 3)
    v = validate_span(source, "MPa")
    assert (v.char_start, v.char_end) == (0, 3)
    assert source.count("MPa") == 3


def test_empty_span_is_not_found() -> None:
    source = "Any non-empty source text."
    v = validate_span(source, "")
    assert v.status == STATUS_NOT_FOUND
    assert v.char_start is None and v.char_end is None
    assert find_span(source, "") is None


def test_aggregate_report_counts() -> None:
    source = "Yield strength was 350 MPa; медный купорос raствор."
    spans = [
        "350 MPa",  # exact
        "МЕДНЫЙ КУПОРОС",  # normalized (Cyrillic case)
        "500 GPa",  # not found (hallucinated)
        {"text": "Yield", "char_start": 0, "char_end": 3},  # offset_mismatch ("Yie")
    ]
    report = validate_extraction(source, spans)
    assert isinstance(report, ExtractionReport)
    assert report.total == 4
    assert report.exact == 1
    assert report.normalized == 1
    assert report.not_found == 1
    assert report.offset_mismatch == 1
    assert report.valid == 2
    assert report.invalid == 2
    assert report.all_grounded is False


def test_span_validation_as_dict_roundtrip() -> None:
    source = "Density is 7.8 g/cm3 for steel."
    v = validate_span(source, "7.8 g/cm3")
    d = v.as_dict()
    assert isinstance(v, SpanValidation)
    assert d["status"] == STATUS_EXACT
    assert d["span_text"] == "7.8 g/cm3"
    assert d["char_start"] == 11 and d["char_end"] == 20
    assert d["ok"] is True
    assert set(d) == {
        "status",
        "span_text",
        "char_start",
        "char_end",
        "matched_text",
        "fuzzy_used",
        "ok",
    }
