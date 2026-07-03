"""Tests for caption↔object anchoring (§5.7 / §8.3).

Hand-checkable cases: exact number match (conf 1.0), missing objects (None/0.0),
kind isolation (table never links to a figure), order fallback (conf 0.5), and
multi-caption number matching. RU/EN caption bodies exercised for realism.
"""

from __future__ import annotations

from kg_extractors.caption_linker import CaptionLink, link_captions


def test_exact_table_match_confidence_one() -> None:
    """Table caption №1 links to table {number:1} with confidence 1.0."""
    captions = [{"kind": "table", "number": 1, "text": "Химический состав"}]
    tables = [{"number": 1, "id": "table:d:001"}]
    links = link_captions(captions, tables, figures=[])
    assert len(links) == 1
    assert links[0].target_id == "table:d:001"
    assert links[0].confidence == 1.0


def test_figure_caption_no_figures_is_unlinked() -> None:
    """Figure caption №3 with zero figures → target_id None, confidence 0.0."""
    captions = [{"kind": "figure", "number": 3, "text": "Hardness vs T"}]
    links = link_captions(captions, tables=[], figures=[])
    assert links[0].target_id is None
    assert links[0].confidence == 0.0


def test_kind_is_respected_table_never_links_to_figure() -> None:
    """A table caption never anchors to a figure object of the same number."""
    captions = [{"kind": "table", "number": 1, "text": "Table body"}]
    figures = [{"number": 1, "id": "fig:x:001"}]
    links = link_captions(captions, tables=[], figures=figures)
    assert links[0].target_id is None
    assert links[0].confidence == 0.0


def test_order_fallback_confidence_half() -> None:
    """Caption №9 with a single figure {number:2} links by order at conf 0.5."""
    captions = [{"kind": "figure", "number": 9, "text": "Рис. подпись"}]
    figures = [{"number": 2, "id": "fig:x"}]
    links = link_captions(captions, tables=[], figures=figures)
    assert links[0].target_id == "fig:x"
    assert links[0].confidence == 0.5


def test_two_table_captions_match_by_number() -> None:
    """Two table captions (1, 2) each anchor to the table of the same number."""
    captions = [
        {"kind": "table", "number": 1, "text": "first"},
        {"kind": "table", "number": 2, "text": "second"},
    ]
    tables = [
        {"number": 1, "id": "table:d:001"},
        {"number": 2, "id": "table:d:002"},
    ]
    links = link_captions(captions, tables, figures=[])
    assert [ln.target_id for ln in links] == ["table:d:001", "table:d:002"]
    assert all(ln.confidence == 1.0 for ln in links)


def test_result_length_equals_caption_count() -> None:
    """Result length equals the number of input captions (linked or not)."""
    captions = [
        {"kind": "table", "number": 1, "text": "a"},
        {"kind": "figure", "number": 7, "text": "b"},
        {"kind": "table", "number": 5, "text": "c"},
    ]
    tables = [{"number": 1, "id": "table:d:001"}]
    links = link_captions(captions, tables, figures=[])
    assert len(links) == len(captions)


def test_as_dict_of_unlinked_caption() -> None:
    """as_dict() of an unlinked caption exposes target_id None and confidence 0.0."""
    captions = [{"kind": "figure", "number": 4, "text": "no figure here"}]
    links = link_captions(captions, tables=[], figures=[])
    d = links[0].as_dict()
    assert d["target_id"] is None
    assert d["confidence"] == 0.0
    assert d["kind"] == "figure"
    assert d["number"] == 4


def test_frozen_dataclass_is_immutable() -> None:
    """CaptionLink is frozen — attribute assignment raises."""
    link = CaptionLink(
        kind="table",
        number=1,
        caption_text="x",
        target_id="table:d:001",
        confidence=1.0,
    )
    try:
        link.confidence = 0.0  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - guards the frozen contract
        raise AssertionError("CaptionLink must be frozen")
