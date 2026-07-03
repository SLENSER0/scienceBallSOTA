"""Document-metadata tests — DOI/authors/journal/year/title (§5.7)."""

from __future__ import annotations

from kg_extractors.doc_metadata import (
    DocMeta,
    extract_authors,
    extract_doc_metadata,
    extract_doi,
    extract_journal,
    extract_title,
    extract_year,
)

# A representative reference line as it appears in a parsed paper surface.
_REF = (
    "Ivanov A., Petrov B. Fatigue of Ti-6Al-4V. Acta Materialia, 2020. "
    "doi:10.1016/j.actamat.2020.01.001."
)

# ---------------------------------------------------------------------------
# extract_doi
# ---------------------------------------------------------------------------


def test_doi_basic() -> None:
    text = "... doi:10.1016/j.actamat.2020.01.001 ..."
    assert extract_doi(text) == "10.1016/j.actamat.2020.01.001"


def test_doi_trailing_period_stripped() -> None:
    text = "See doi:10.1016/j.actamat.2020.01.001."
    assert extract_doi(text) == "10.1016/j.actamat.2020.01.001"


def test_doi_trailing_bracket_stripped() -> None:
    text = "(doi:10.1103/PhysRevB.101.014103)"
    assert extract_doi(text) == "10.1103/PhysRevB.101.014103"


def test_doi_absent_is_none() -> None:
    assert extract_doi("A note with no digital object identifier at all.") is None


def test_doi_registrant_too_short_is_none() -> None:
    # ``10.12/x`` has only a 2-digit registrant → not a DOI (needs 4–9).
    assert extract_doi("ref 10.12/x here") is None


# ---------------------------------------------------------------------------
# extract_year
# ---------------------------------------------------------------------------


def test_year_found() -> None:
    assert extract_year("Published in 2020 by the society.") == 2020


def test_year_out_of_window_is_none() -> None:
    assert extract_year("An old text from 1969 and a far 2050.") is None


def test_year_not_glued_to_longer_number() -> None:
    assert extract_year("serial 12020340") is None


# ---------------------------------------------------------------------------
# extract_authors
# ---------------------------------------------------------------------------


def test_authors_two() -> None:
    assert len(extract_authors("Ivanov A., Petrov B.")) == 2


def test_authors_values() -> None:
    assert extract_authors("Ivanov A., Petrov B.") == ("Ivanov A.", "Petrov B.")


def test_authors_multiple_initials() -> None:
    assert extract_authors("Smith J.R.") == ("Smith J.R.",)


def test_authors_dedup_preserves_order() -> None:
    assert extract_authors("Ivanov A., Petrov B., Ivanov A.") == ("Ivanov A.", "Petrov B.")


def test_authors_none() -> None:
    assert extract_authors("no bylines in this plain sentence") == ()


# ---------------------------------------------------------------------------
# extract_title
# ---------------------------------------------------------------------------


def test_title_from_label() -> None:
    assert extract_title("Title: Fatigue of Ti-6Al-4V\nbody") == "Fatigue of Ti-6Al-4V"


def test_title_from_h1() -> None:
    assert extract_title("# Creep Behaviour\n\ntext") == "Creep Behaviour"


def test_title_hint_used_when_absent() -> None:
    assert extract_title("plain body with no heading", title_hint="Hinted") == "Hinted"


def test_title_none_when_nothing() -> None:
    assert extract_title("plain body with no heading") is None


# ---------------------------------------------------------------------------
# extract_journal
# ---------------------------------------------------------------------------


def test_journal_from_label() -> None:
    assert extract_journal("Journal: Acta Materialia") == "Acta Materialia"


def test_journal_published_in() -> None:
    assert extract_journal("Published in Scripta Materialia") == "Scripta Materialia"


def test_journal_none() -> None:
    assert extract_journal("no venue mentioned") is None


# ---------------------------------------------------------------------------
# extract_doc_metadata + DocMeta
# ---------------------------------------------------------------------------


def test_metadata_aggregate() -> None:
    meta = extract_doc_metadata(_REF, title_hint="Fallback title")
    assert isinstance(meta, DocMeta)
    assert meta.doi == "10.1016/j.actamat.2020.01.001"
    assert meta.year == 2020
    assert meta.authors == ("Ivanov A.", "Petrov B.")


def test_metadata_doi_present() -> None:
    doc = "... doi:10.1016/j.actamat.2020.01.001 ..."
    assert extract_doc_metadata(doc).doi == "10.1016/j.actamat.2020.01.001"


def test_metadata_no_doi_is_none() -> None:
    assert extract_doc_metadata("plain note, no identifier").doi is None


def test_metadata_title_hint_used() -> None:
    meta = extract_doc_metadata("body text without any heading", title_hint="Hinted Title")
    assert meta.title == "Hinted Title"


def test_metadata_frozen() -> None:
    meta = extract_doc_metadata(_REF)
    try:
        meta.doi = "x"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject mutation
        raise AssertionError("DocMeta must be frozen")


def test_as_dict_authors_is_list() -> None:
    meta = extract_doc_metadata(_REF)
    assert isinstance(meta.as_dict()["authors"], list)


def test_as_dict_shape() -> None:
    meta = extract_doc_metadata("Title: T\nIvanov A. doi:10.1016/x.2020.1.\nJournal: J")
    assert meta.as_dict() == {
        "title": "T",
        "authors": ["Ivanov A."],
        "doi": "10.1016/x.2020.1",
        "year": 2020,
        "journal": "J",
    }
