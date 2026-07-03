"""Tests for RIS citation export — тесты экспорта цитат в RIS (§22.6)."""

from __future__ import annotations

from kg_common.ris_export import (
    RisRecord,
    paper_to_record,
    parse_ris,
    records_to_ris,
)

# A representative two-author paper with a DOI — типичная статья.
PAPER = {
    "type": "paper",
    "authors": ["Ivanov, I.", "Petrova, A."],
    "title": "On Sintered Alumina",
    "year": 2020,
    "doi": "10.1000/abcd",
}


def test_type_paper_first_ty_last_er() -> None:
    """(1) type=paper -> first tag ('TY','JOUR'), last ('ER','')."""
    rec = paper_to_record(PAPER)
    assert rec.tags[0] == ("TY", "JOUR")
    assert rec.tags[-1] == ("ER", "")


def test_two_authors_two_au_tags_in_order() -> None:
    """(2) two authors -> two ('AU', name) tags in input order."""
    rec = paper_to_record(PAPER)
    au = [t for t in rec.tags if t[0] == "AU"]
    assert au == [("AU", "Ivanov, I."), ("AU", "Petrova, A.")]


def test_title_tag() -> None:
    """(3) title -> ('TI', title)."""
    rec = paper_to_record(PAPER)
    assert ("TI", "On Sintered Alumina") in rec.tags


def test_year_2020_py_tag() -> None:
    """(4) year 2020 -> ('PY', '2020') as a string."""
    rec = paper_to_record(PAPER)
    assert ("PY", "2020") in rec.tags


def test_to_ris_line_format_exact() -> None:
    """(5) TY line is exactly 'TY  - JOUR' (tag, two spaces, dash, space)."""
    rec = paper_to_record(PAPER)
    lines = rec.to_ris().split("\n")
    assert lines[0] == "TY  - JOUR"
    # The bare terminator line has an empty value but keeps the separator.
    assert lines[-1] == "ER  - "


def test_missing_doi_no_do_line() -> None:
    """(6) missing doi -> no 'DO' tag / no 'DO' line."""
    meta = {k: v for k, v in PAPER.items() if k != "doi"}
    rec = paper_to_record(meta)
    assert all(code != "DO" for code, _ in rec.tags)
    assert "DO" not in rec.to_ris()

    # Present doi -> a DO line does appear.
    rec_doi = paper_to_record(PAPER)
    assert ("DO", "10.1000/abcd") in rec_doi.tags


def test_records_to_ris_each_ends_with_er() -> None:
    """(7) records_to_ris joins records; each ends with 'ER  - '."""
    second = {
        "type": "book",
        "authors": ["Smith, J."],
        "title": "Ceramics",
        "year": 2019,
    }
    out = records_to_ris([PAPER, second])
    blocks = out.split("\n\n")
    assert len(blocks) == 2
    for block in blocks:
        assert block.split("\n")[-1] == "ER  - "
    # Non-paper type maps to its own RIS code.
    assert blocks[1].startswith("TY  - BOOK")


def test_parse_round_trip() -> None:
    """(8) parse_ris(to_ris(rec)) reproduces rec.tags exactly."""
    rec = paper_to_record(PAPER)
    parsed = parse_ris(rec.to_ris())
    assert len(parsed) == 1
    assert parsed[0].tags == rec.tags


def test_parse_multiple_records_round_trip() -> None:
    """records_to_ris then parse_ris recovers every record's tags."""
    second = {"type": "report", "authors": ["Doe, J."], "title": "R", "year": 2021}
    metas = [PAPER, second]
    text = records_to_ris(metas)
    parsed = parse_ris(text)
    expected = [paper_to_record(m).tags for m in metas]
    assert [p.tags for p in parsed] == expected


def test_as_dict_shape() -> None:
    """as_dict exposes ordered [code, value] pairs including duplicates."""
    rec = paper_to_record(PAPER)
    d = rec.as_dict()
    assert d["tags"][0] == ["TY", "JOUR"]
    assert ["AU", "Ivanov, I."] in d["tags"]
    assert d["tags"][-1] == ["ER", ""]


def test_empty_records_to_ris() -> None:
    """No metadata -> empty string."""
    assert records_to_ris([]) == ""


def test_to_ris_appends_er_when_absent() -> None:
    """to_ris terminates a record even if tags omit the ER sentinel."""
    rec = RisRecord(tags=(("TY", "JOUR"), ("TI", "X")))
    assert rec.to_ris().split("\n")[-1] == "ER  - "
