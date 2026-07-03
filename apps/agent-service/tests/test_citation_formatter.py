"""Hand-checked tests for §13.15 citation formatting.

Pure-python, no store / no LLM: build EvidenceRef-shaped span pointers (the same
model the evidence-assembler produces) and assert the exact numbering, reference
block and dangling-marker validation. Every expected value is spelled out so the
test is verifiable by hand.
"""

from __future__ import annotations

import pytest
from agent_service.citation_formatter import (
    Citation,
    citation_map,
    format_reference_list,
    inject_markers,
    number_citations,
)

from kg_common import EvidenceRef


def _ref(
    evidence_id: str,
    *,
    doc_id: str | None = None,
    page: int | None = None,
    text: str | None = None,
    source_id: str = "claim:x",
) -> EvidenceRef:
    """Build an EvidenceRef-shaped span pointer for the formatter under test."""
    return EvidenceRef(
        evidence_id=evidence_id,
        source_id=source_id,
        doc_id=doc_id,
        page=page,
        text=text,
    )


# ---------------------------------------------------------------------------
# number_citations: numbering, dedup, stable order
# ---------------------------------------------------------------------------
def test_numbering_starts_at_one_and_dedups_same_evidence_id() -> None:
    # Same evidence_id appears twice → one citation, numbered [1]; the distinct
    # second span becomes [2] (numbering starts at 1, no gap from the dedup).
    refs = [
        _ref("ev:a", doc_id="doc:p1", page=3, text="первый"),
        _ref("ev:a", doc_id="doc:p1", page=3, text="первый (дубль)"),
        _ref("ev:b", doc_id="doc:p2", page=7, text="второй"),
    ]
    cits = number_citations(refs)
    assert [c.n for c in cits] == [1, 2]
    assert [c.evidence_id for c in cits] == ["ev:a", "ev:b"]
    assert cits[0].marker == "[1]"
    # the retained ev:a is the FIRST occurrence (its snippet, not the duplicate's).
    assert cits[0].snippet == "первый"


def test_two_docs_get_two_numbers() -> None:
    refs = [
        _ref("ev:1", doc_id="doc:alpha", page=1, text="A"),
        _ref("ev:2", doc_id="doc:beta", page=2, text="B"),
    ]
    cits = number_citations(refs)
    assert len(cits) == 2
    assert (cits[0].n, cits[0].doc_id) == (1, "doc:alpha")
    assert (cits[1].n, cits[1].doc_id) == (2, "doc:beta")


def test_stable_order_follows_input_order() -> None:
    # Numbers are assigned in the exact order the refs arrive (детерминизм).
    refs = [_ref(f"ev:{k}", doc_id=f"doc:{k}", page=i) for i, k in enumerate("dbca")]
    cits = number_citations(refs)
    assert [c.evidence_id for c in cits] == ["ev:d", "ev:b", "ev:c", "ev:a"]
    assert [c.n for c in cits] == [1, 2, 3, 4]


def test_empty_input_returns_empty_list() -> None:
    assert number_citations([]) == []
    assert format_reference_list([]) == ""


def test_snippet_is_truncated_with_ellipsis() -> None:
    long_text = "a" * 200
    cit = number_citations([_ref("ev:long", doc_id="doc:x", page=1, text=long_text)])[0]
    assert cit.snippet == "a" * 160 + "…"
    assert len(cit.snippet) == 161
    # a short snippet is passed through verbatim (no truncation, no ellipsis).
    short = number_citations([_ref("ev:s", text="короткий")])[0]
    assert short.snippet == "короткий"


def test_as_dict_exact_shape() -> None:
    cit = number_citations([_ref("ev:a", doc_id="doc:p1", page=3, text="фрагмент")])[0]
    assert cit.as_dict() == {
        "n": 1,
        "evidence_id": "ev:a",
        "doc_id": "doc:p1",
        "page": 3,
        "snippet": "фрагмент",
    }


# ---------------------------------------------------------------------------
# format_reference_list: doc + page rendering (RU/EN)
# ---------------------------------------------------------------------------
def test_reference_list_contains_doc_and_page() -> None:
    cits = number_citations(
        [
            _ref("ev:a", doc_id="doc:paper1", page=3, text="скорость 1.2 см/с"),
            _ref("ev:b", doc_id="doc:paper2", page=7, text="flow velocity 1.1 cm/s"),
        ]
    )
    block = format_reference_list(cits)
    lines = block.splitlines()
    assert len(lines) == 2
    assert lines[0] == "[1] doc:paper1, с. 3 — скорость 1.2 см/с"
    assert lines[1] == "[2] doc:paper2, с. 7 — flow velocity 1.1 cm/s"


def test_reference_list_omits_missing_page_and_doc() -> None:
    cits = number_citations([_ref("ev:x", doc_id=None, page=None, text="без метаданных")])
    line = format_reference_list(cits)
    assert line == "[1] (без документа / no document) — без метаданных"
    assert "с." not in line  # no page abbreviation when page is missing


# ---------------------------------------------------------------------------
# inject_markers: no-op passthrough + dangling validation
# ---------------------------------------------------------------------------
def test_inject_markers_passes_through_when_all_cited() -> None:
    cits = number_citations(
        [_ref("ev:a", doc_id="doc:p1", page=1), _ref("ev:b", doc_id="doc:p2", page=2)]
    )
    text = "Католит подаётся со скоростью 1.2 см/с [1], что согласуется с [2]."
    out = inject_markers(text, citation_map(cits))
    assert out == text  # unchanged — pure passthrough


def test_inject_markers_raises_on_dangling_marker() -> None:
    cits = number_citations([_ref("ev:a", doc_id="doc:p1", page=1)])  # only [1] exists
    text = "Есть довод [1], но здесь висячая ссылка [9]."
    with pytest.raises(ValueError, match=r"\[9\]"):
        inject_markers(text, citation_map(cits))


def test_citation_map_indexes_by_number() -> None:
    cits = [
        Citation(n=1, evidence_id="ev:a", doc_id="d1", page=1, snippet="a"),
        Citation(n=2, evidence_id="ev:b", doc_id="d2", page=2, snippet="b"),
    ]
    mapping = citation_map(cits)
    assert set(mapping) == {1, 2}
    assert mapping[2].evidence_id == "ev:b"
    # text using only in-range markers validates cleanly.
    assert inject_markers("см. [1] и [2]", mapping) == "см. [1] и [2]"
