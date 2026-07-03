"""BibTeX export tests — экспорт списка литературы (§22.6)."""

from __future__ import annotations

from kg_common.bibtex_export import (
    BibEntry,
    dedupe_keys,
    paper_to_entry,
    papers_to_bibtex,
)

# One well-formed paper: Smith 2020 — базовая запись для проверок.
SMITH = {
    "doc_id": "d1",
    "title": "On Copper Alloys",
    "authors": ["Smith, J."],
    "year": 2020,
    "doi": "10.1/abc",
    "venue": "Journal of Metals",
}


def test_cite_key_lastname_year() -> None:
    # Assertion (1): "Smith, J." + 2020 -> "smith2020" (lowercased, comma-split).
    entry = paper_to_entry({"author": "Smith, J.", "year": 2020})
    assert entry.key == "smith2020"


def test_to_bibtex_delimiters() -> None:
    # Assertion (2): the block opens with @article{smith2020, and ends with }.
    bib = paper_to_entry(SMITH).to_bibtex()
    assert bib.startswith("@article{smith2020,")
    assert bib.endswith("}")


def test_title_wrapped_in_braces() -> None:
    # Assertion (3): the title renders as `title = {...}`.
    bib = paper_to_entry(SMITH).to_bibtex()
    assert "title = {On Copper Alloys}" in bib


def test_ampersand_escaped_in_venue() -> None:
    # Assertion (4): "&" in the venue becomes "\&" (BibTeX-significant char).
    entry = paper_to_entry({"authors": ["Doe, A."], "year": 1999, "venue": "Metals & Alloys"})
    assert entry.fields["journal"] == r"Metals \& Alloys"
    assert r"journal = {Metals \& Alloys}" in entry.to_bibtex()


def test_missing_doi_emits_no_line() -> None:
    # Assertion (5): a paper without a doi has no doi field/line.
    meta = {k: v for k, v in SMITH.items() if k != "doi"}
    entry = paper_to_entry(meta)
    assert "doi" not in entry.fields
    assert "doi" not in entry.to_bibtex()


def test_dedupe_same_author_year() -> None:
    # Assertion (6): two identical keys -> smith2020a and smith2020b, in order.
    a = paper_to_entry({"author": "Smith, J.", "year": 2020, "title": "First"})
    b = paper_to_entry({"author": "Smith, A.", "year": 2020, "title": "Second"})
    assert a.key == b.key == "smith2020"
    out = dedupe_keys([a, b])
    assert [e.key for e in out] == ["smith2020a", "smith2020b"]
    # Fields survive the re-key (frozen copy, not a fresh empty entry).
    assert out[0].fields["title"] == "First"


def test_dedupe_leaves_unique_keys() -> None:
    # A key seen only once is not suffixed.
    a = paper_to_entry({"author": "Smith, J.", "year": 2020})
    b = paper_to_entry({"author": "Jones, K.", "year": 2021})
    assert [e.key for e in dedupe_keys([a, b])] == ["smith2020", "jones2021"]


def test_multiple_authors_joined_with_and() -> None:
    # Assertion (7): authors are joined with " and "; cite key uses the first.
    entry = paper_to_entry({"authors": ["Smith, J.", "Doe, A.", "Roe, B."], "year": 2020})
    assert entry.fields["author"] == "Smith, J. and Doe, A. and Roe, B."
    assert entry.key == "smith2020"


def test_papers_to_bibtex_empty_and_blank_separated() -> None:
    # Assertion (8): [] -> "" and entries are separated by a blank line.
    assert papers_to_bibtex([]) == ""
    metas = [
        {"author": "Smith, J.", "year": 2020, "title": "First"},
        {"author": "Jones, K.", "year": 2021, "title": "Second"},
    ]
    doc = papers_to_bibtex(metas)
    blocks = doc.split("\n\n")
    assert len(blocks) == 2  # exactly one blank line between the two blocks
    assert blocks[0].startswith("@article{smith2020,")
    assert blocks[1].startswith("@article{jones2021,")


def test_ascii_fold_cyrillic_lastname() -> None:
    # Non-ASCII family names fold to bare latin (Cyrillic stripped) before keying.
    entry = paper_to_entry({"author": "Иванов, П.", "year": 2020})
    # "Иванов" has no ASCII latin form here -> stripped to empty -> "anon" stem.
    assert entry.key == "anon2020"
    # A diacritic name keeps its latin base letters.
    assert paper_to_entry({"author": "Müller, H.", "year": 2019}).key == "muller2019"


def test_as_dict_roundtrip() -> None:
    entry = paper_to_entry(SMITH)
    d = entry.as_dict()
    assert d["key"] == "smith2020"
    assert d["entry_type"] == "article"
    assert d["fields"]["title"] == "On Copper Alloys"
    # as_dict returns a copy — mutating it must not touch the frozen entry.
    d["fields"]["title"] = "changed"
    assert entry.fields["title"] == "On Copper Alloys"


def test_escapes_braces_in_value() -> None:
    # "{" and "}" in a value are backslash-escaped so BibTeX groups don't break.
    entry = paper_to_entry({"author": "Smith, J.", "year": 2020, "title": "a {b} c"})
    assert entry.fields["title"] == r"a \{b\} c"


def test_bibentry_is_frozen() -> None:
    entry = BibEntry(key="k", entry_type="article", fields={})
    try:
        entry.key = "other"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("BibEntry should be frozen")
