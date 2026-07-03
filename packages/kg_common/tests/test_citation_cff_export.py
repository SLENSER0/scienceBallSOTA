"""Tests for CITATION.cff export — тесты экспорта CITATION.cff (§22)."""

from __future__ import annotations

from kg_common.citation_cff_export import (
    CffCitation,
    build_citation,
    to_cff,
)


def _sample() -> CffCitation:
    """One-author dataset citation used across the assertions — образец."""
    return build_citation(
        title="Science-Ball KG",
        version="1.0.0",
        authors=[("Ivanov", "A")],
        cff_type="dataset",
    )


def test_first_line_is_cff_version() -> None:
    """Output must open with the exact schema-version line."""
    text = to_cff(_sample())
    assert text.splitlines()[0] == "cff-version: 1.2.0"


def test_contains_type_dataset() -> None:
    """Default cff_type renders a ``type: dataset`` line."""
    assert "type: dataset" in to_cff(_sample())


def test_single_author_block() -> None:
    """One author renders family-names / given-names with CFF indentation."""
    text = to_cff(_sample())
    assert "  - family-names: Ivanov" in text
    assert "    given-names: A" in text


def test_doi_none_omits_line() -> None:
    """A ``None`` doi produces no ``doi:`` line at all."""
    text = to_cff(_sample())
    assert not any(line.startswith("doi:") for line in text.splitlines())


def test_doi_present_renders_line() -> None:
    """A doi renders a ``doi: 10.x/y`` line verbatim."""
    c = build_citation(
        title="X",
        version="1.0.0",
        authors=[("Ivanov", "A")],
        doi="10.x/y",
    )
    assert "doi: 10.x/y" in to_cff(c)


def test_title_with_colon_is_quoted() -> None:
    """A title containing ``:`` is double-quoted to keep YAML unambiguous."""
    c = build_citation(
        title="Science-Ball: A KG",
        version="1.0.0",
        authors=[("Ivanov", "A")],
    )
    assert 'title: "Science-Ball: A KG"' in to_cff(c)


def test_date_released_renders_line() -> None:
    """``date_released`` renders a ``date-released:`` line."""
    c = build_citation(
        title="X",
        version="1.0.0",
        authors=[("Ivanov", "A")],
        date_released="2026-07-03",
    )
    assert "date-released: 2026-07-03" in to_cff(c)


def test_as_dict_authors_are_2_tuples() -> None:
    """``as_dict()['authors']`` is a list of 2-tuples in input order."""
    d = _sample().as_dict()
    authors = d["authors"]
    assert isinstance(authors, list)
    assert authors == [("Ivanov", "A")]
    assert all(isinstance(a, tuple) and len(a) == 2 for a in authors)


def test_message_line_present() -> None:
    """A ``message:`` line sits directly after the version line."""
    lines = to_cff(_sample()).splitlines()
    assert lines[1].startswith("message: ")


def test_multiple_authors_preserve_order() -> None:
    """Authors render in input order, two lines each."""
    c = build_citation(
        title="X",
        version="1.0.0",
        authors=[("Ivanov", "A"), ("Petrov", "B")],
    )
    text = to_cff(c)
    assert text.index("Ivanov") < text.index("Petrov")
    assert "    given-names: B" in text


def test_frozen_dataclass_is_immutable() -> None:
    """CffCitation is frozen — attribute assignment raises."""
    c = _sample()
    try:
        c.version = "2.0.0"  # type: ignore[misc]
    except (AttributeError, TypeError):
        return
    raise AssertionError("expected frozen dataclass to reject assignment")
