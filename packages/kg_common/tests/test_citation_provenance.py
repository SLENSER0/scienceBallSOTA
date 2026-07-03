"""Tests for citation provenance — тесты происхождения цитат (§10.10/§6.2)."""

from __future__ import annotations

from kg_common.citation_provenance import (
    CitationProvenance,
    enrich_all,
    enrich_citation,
    missing_provenance,
)


def test_as_dict_drops_none_fields() -> None:
    """as_dict omits None-valued optional keys — None-поля выпадают."""
    prov = CitationProvenance("d1", "alice", "L1", "v2", "fresh", None, None, "accepted")
    d = prov.as_dict()
    assert "extractor" not in d
    assert "model" not in d
    assert d == {
        "doc_id": "d1",
        "owner": "alice",
        "lab": "L1",
        "version": "v2",
        "freshness": "fresh",
        "review_status": "accepted",
    }


def test_as_dict_always_keeps_doc_id() -> None:
    """doc_id survives even when every optional field is None — doc_id всегда."""
    assert CitationProvenance("only-id").as_dict() == {"doc_id": "only-id"}


def test_as_dict_retains_version_when_present() -> None:
    """version is kept when set — version сохраняется."""
    d = CitationProvenance("d9", version="v7").as_dict()
    assert d["version"] == "v7"
    assert d == {"doc_id": "d9", "version": "v7"}


def test_enrich_citation_adds_owner() -> None:
    """enrich_citation surfaces owner under provenance — owner под provenance."""
    out = enrich_citation({"doc_id": "d1"}, {"owner": "alice", "lab": "L1"})
    assert out["provenance"]["owner"] == "alice"
    assert out["provenance"]["lab"] == "L1"
    assert out["provenance"]["doc_id"] == "d1"


def test_enrich_citation_does_not_mutate_input() -> None:
    """The original citation gains no provenance key — вход не мутируется."""
    citation = {"doc_id": "d1", "text": "snippet"}
    out = enrich_citation(citation, {"owner": "bob"})
    assert "provenance" not in citation
    assert out is not citation
    assert out["text"] == "snippet"
    assert out["provenance"]["owner"] == "bob"


def test_enrich_citation_empty_source_meta_has_no_owner() -> None:
    """Empty metadata yields provenance with only doc_id — только doc_id."""
    out = enrich_citation({"doc_id": "d1"}, {})
    assert "owner" not in out["provenance"]
    assert out["provenance"] == {"doc_id": "d1"}


def test_enrich_all_maps_two_citations() -> None:
    """enrich_all resolves each citation via the source index — обе цитаты."""
    citations = [{"doc_id": "a"}, {"doc_id": "b"}]
    source_index = {
        "a": {"owner": "alice", "version": "v1"},
        "b": {"owner": "bob", "lab": "L2"},
    }
    out = enrich_all(citations, source_index)
    assert len(out) == 2
    assert out[0]["provenance"] == {"doc_id": "a", "owner": "alice", "version": "v1"}
    assert out[1]["provenance"] == {"doc_id": "b", "owner": "bob", "lab": "L2"}


def test_enrich_all_missing_source_yields_bare_provenance() -> None:
    """A citation with no source entry gets doc_id-only provenance — без метаданных."""
    out = enrich_all([{"doc_id": "z"}], {})
    assert out[0]["provenance"] == {"doc_id": "z"}


def test_missing_provenance_reports_unknown_doc_id() -> None:
    """missing_provenance lists doc_ids absent from the index — отсутствующие."""
    assert missing_provenance([{"doc_id": "x"}], {}) == ["x"]


def test_missing_provenance_filters_known_ids() -> None:
    """Known doc_ids are excluded; unknown remain in order — фильтрация."""
    citations = [{"doc_id": "a"}, {"doc_id": "b"}, {"doc_id": "c"}]
    source_index = {"a": {"owner": "alice"}, "c": {"owner": "carol"}}
    assert missing_provenance(citations, source_index) == ["b"]


def test_meta_non_string_values_are_coerced() -> None:
    """Non-string metadata values become strings — приведение к строке."""
    out = enrich_citation({"doc_id": "d1"}, {"version": 3})
    assert out["provenance"]["version"] == "3"
