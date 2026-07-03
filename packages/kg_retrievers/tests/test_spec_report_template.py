"""Tests for the §24.16 technical-assignment (ТЗ) report template."""

from __future__ import annotations

from kg_retrievers.spec_report_template import (
    SpecReport,
    build_spec_report,
    section_titles,
    validate_spec_report,
)


def _full_report() -> SpecReport:
    """A fully-populated, well-formed ТЗ report."""
    return build_spec_report(
        problem="Выбрать метод синтеза для катализатора",
        input_conditions=["бюджет ограничен", "срок 6 месяцев"],
        compared_technologies=["золь-гель", "гидротермальный"],
        recommendation="Использовать золь-гель метод",
        risks=["масштабирование не проверено"],
        evidence_ids=["ev1", "ev2"],
    )


def test_recommendation_without_evidence() -> None:
    """(1) Recommendation set but no evidence → recommendation_without_evidence."""
    report = build_spec_report(
        problem="p",
        compared_technologies=["a", "b"],
        recommendation="выбрать a",
        evidence_ids=[],
    )
    assert "recommendation_without_evidence" in validate_spec_report(report)
    assert "no_recommendation" not in validate_spec_report(report)


def test_fully_populated_is_valid() -> None:
    """(2) A fully-populated report validates with no issues."""
    assert validate_spec_report(_full_report()) == ()


def test_to_markdown_has_all_six_ru_headings_in_order() -> None:
    """(3) to_markdown contains the six RU headings in canonical order."""
    md = _full_report().to_markdown()
    expected = [
        "## Проблема",
        "## Входные условия",
        "## Сравниваемые технологии",
        "## Рекомендация",
        "## Риски",
        "## Доказательная база",
    ]
    positions = [md.index(h) for h in expected]
    assert all(p >= 0 for p in positions)
    assert positions == sorted(positions)
    # section_titles exposes the same RU order (without the ## prefix).
    assert section_titles() == [h[3:] for h in expected]


def test_empty_problem_flagged() -> None:
    """(4) An empty problem → missing_problem."""
    report = build_spec_report(
        problem="   ",
        compared_technologies=["a", "b"],
        recommendation="r",
        evidence_ids=["e"],
    )
    assert "missing_problem" in validate_spec_report(report)


def test_as_dict_from_dict_round_trip() -> None:
    """(5) as_dict / from_dict round-trip is stable."""
    report = _full_report()
    assert SpecReport.from_dict(report.as_dict()) == report


def test_tuple_fields_dedupe_preserving_order() -> None:
    """(6) Tuple fields dedupe while preserving first-seen order."""
    report = build_spec_report(
        problem="p",
        input_conditions=["x", "y", "x", "  y  ", "z"],
        compared_technologies=["b", "a", "b"],
        risks=["r1", "r1", "r2"],
        evidence_ids=["e1", "e2", "e1"],
    )
    assert report.input_conditions == ("x", "y", "z")
    assert report.compared_technologies == ("b", "a")
    assert report.risks == ("r1", "r2")
    assert report.evidence_ids == ("e1", "e2")


def test_no_compared_technologies_flagged() -> None:
    """(7) No compared technologies → no_compared_technologies."""
    report = build_spec_report(
        problem="p",
        compared_technologies=[],
        recommendation="r",
        evidence_ids=["e"],
    )
    assert "no_compared_technologies" in validate_spec_report(report)


def test_no_recommendation_code() -> None:
    """A blank recommendation yields no_recommendation (not the evidence code)."""
    report = build_spec_report(
        problem="p",
        compared_technologies=["a", "b"],
        recommendation="",
    )
    issues = validate_spec_report(report)
    assert "no_recommendation" in issues
    assert "recommendation_without_evidence" not in issues
