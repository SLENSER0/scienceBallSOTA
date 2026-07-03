"""Structured report-section assembly tests (§24.17).

Hand-checked against a fully-populated report whose bodies are:

- summary        (prose)  "Титан превосходит сталь по удельной прочности."
- methods        (list)   ["Литьё под давлением", "Аддитивное производство"]
- evidence       (list)   ["ev:1 — прочность", "ev:2 — коррозия"]
- gaps           (list)   ["Нет данных по усталости"]
- contradictions (list)   ["ev:1 против ev:3 по цене"]
- recommendations(list)   ["Выбрать титан для корпуса"]
- pilot_checks   (list)   ["Проверить усталость на 10 образцах"]

so the canonical order Краткий вывод / Методы и решения / Доказательная база /
Пробелы / Противоречия / Рекомендации / Что проверить пилотно is fully realised.
"""

from __future__ import annotations

from kg_retrievers.report_sections import (
    KIND_LIST,
    KIND_PROSE,
    Report,
    Section,
    assemble_sections,
    section_titles,
)

CANONICAL_TITLES = [
    "Краткий вывод",
    "Методы и решения",
    "Доказательная база",
    "Пробелы",
    "Противоречия",
    "Рекомендации",
    "Что проверить пилотно",
]


def _full_report() -> Report:
    return assemble_sections(
        summary="Титан превосходит сталь по удельной прочности.",
        methods=["Литьё под давлением", "Аддитивное производство"],
        evidence=["ev:1 — прочность", "ev:2 — коррозия"],
        gaps=["Нет данных по усталости"],
        contradictions=["ev:1 против ev:3 по цене"],
        recommendations=["Выбрать титан для корпуса"],
        pilot_checks=["Проверить усталость на 10 образцах"],
    )


def test_to_markdown_headings_in_canonical_order() -> None:
    # Every populated section renders as a `## heading`, in the fixed canonical order.
    md = _full_report().to_markdown()
    headings = [line[len("## ") :] for line in md.splitlines() if line.startswith("## ")]
    assert headings == CANONICAL_TITLES
    assert md.endswith("\n")


def test_empty_sections_omitted() -> None:
    # Empty list, empty string and None bodies are all skipped — only content survives.
    report = assemble_sections(
        summary="Вывод есть",
        methods=[],  # empty list → skipped
        evidence="",  # empty string → skipped
        gaps=None,  # None → skipped
        contradictions=["Есть противоречие"],
    )
    assert report.titles() == ["Краткий вывод", "Противоречия"]
    md = report.to_markdown()
    assert "## Методы и решения" not in md
    assert "## Доказательная база" not in md
    assert "## Пробелы" not in md
    assert "## Краткий вывод" in md
    assert "## Противоречия" in md


def test_recommendations_optional() -> None:
    # Omitting recommendations (default None) drops the section; providing it adds it.
    without = assemble_sections(
        summary="s", methods=["m"], evidence=["e"], gaps=["g"], contradictions=["c"]
    )
    assert "Рекомендации" not in without.titles()
    assert "## Рекомендации" not in without.to_markdown()

    with_reco = assemble_sections(
        summary="s",
        methods=["m"],
        evidence=["e"],
        gaps=["g"],
        contradictions=["c"],
        recommendations=["Сделать X"],
    )
    assert "Рекомендации" in with_reco.titles()
    assert "## Рекомендации" in with_reco.to_markdown()
    assert "- Сделать X" in with_reco.to_markdown()


def test_pilot_check_section_present_when_given() -> None:
    # The "Что проверить пилотно" section appears only when pilot_checks is supplied.
    report = assemble_sections(
        summary="s",
        methods=["m"],
        evidence=["e"],
        gaps=["g"],
        contradictions=["c"],
        pilot_checks=["Проверить усталость"],
    )
    assert "Что проверить пилотно" in report.titles()
    md = report.to_markdown()
    assert "## Что проверить пилотно" in md
    assert "- Проверить усталость" in md

    none_report = assemble_sections(
        summary="s", methods=["m"], evidence=["e"], gaps=["g"], contradictions=["c"]
    )
    assert "Что проверить пилотно" not in none_report.titles()


def test_as_dict_round_trip() -> None:
    # dict → object → dict is stable, and the object itself is reconstructed intact.
    report = _full_report()
    dumped = report.as_dict()
    rebuilt = Report.from_dict(dumped)
    assert rebuilt == report
    assert rebuilt.as_dict() == dumped
    assert set(dumped) == {"sections"}
    assert dumped["sections"][0] == {
        "key": "summary",
        "title": "Краткий вывод",
        "kind": KIND_PROSE,
        "body": ["Титан превосходит сталь по удельной прочности."],
    }
    assert dumped["sections"][1] == {
        "key": "methods",
        "title": "Методы и решения",
        "kind": KIND_LIST,
        "body": ["Литьё под давлением", "Аддитивное производство"],
    }


def test_section_titles_is_full_canonical_schema() -> None:
    # section_titles() is the fixed seven-title schema, regardless of any report.
    assert section_titles() == CANONICAL_TITLES
    assert len(section_titles()) == 7


def test_deterministic() -> None:
    # Same inputs → equal reports, equal dicts and byte-identical markdown.
    first = _full_report()
    second = _full_report()
    assert first == second
    assert first.as_dict() == second.as_dict()
    assert first.to_markdown() == second.to_markdown()


def test_prose_vs_bullet_rendering() -> None:
    # Prose renders as a bare paragraph under its heading; lists render as `- item`.
    report = assemble_sections(
        summary="Единый вывод одной строкой.",
        methods=["Метод А", "Метод Б"],
        evidence=["ev:1"],
        gaps=["Пробел 1"],
        contradictions=["Спор 1"],
    )
    lines = report.to_markdown().splitlines()
    i = lines.index("## Краткий вывод")
    assert lines[i + 1] == "Единый вывод одной строкой."
    j = lines.index("## Методы и решения")
    assert lines[j + 1] == "- Метод А"
    assert lines[j + 2] == "- Метод Б"
    # the summary section is prose, the methods section is a list
    assert report.sections[0].kind == KIND_PROSE
    assert report.sections[1].kind == KIND_LIST


def test_items_stripped_and_blanks_dropped() -> None:
    # Whitespace is trimmed and all-blank items are removed before assembly.
    report = assemble_sections(
        summary="  вывод с пробелами  ",
        methods=["  метод  ", "", "   "],
        evidence=["ev"],
        gaps=["g"],
        contradictions=["c"],
    )
    assert report.sections[0].body == ("вывод с пробелами",)
    assert report.sections[1].body == ("метод",)


def test_section_from_dict_defaults_to_list_kind() -> None:
    # A serialised section missing its kind rebuilds as a bulleted list (safe default).
    section = Section.from_dict({"key": "gaps", "title": "Пробелы", "body": ["g1"]})
    assert section.kind == KIND_LIST
    assert section.body == ("g1",)
