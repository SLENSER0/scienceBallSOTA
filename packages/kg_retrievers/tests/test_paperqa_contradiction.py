"""Tests for PaperQA2 / ContraCrow cross-source contradiction detection (§15.4 / §13).

Проверяем кросс-документное выявление противоречий: расхождение числовых значений
>=30%, противоположная полярность, самосогласованность внутри документа, изоляция
разных субъектов/свойств, метрика плотности противоречий и сериализация as_dict.
Модуль должен цитировать первоисточник PaperQA2 (arXiv:2409.13740).
"""

from __future__ import annotations

from kg_retrievers import paperqa_contradiction as pqc
from kg_retrievers.paperqa_contradiction import (
    ContradictionPair,
    contradiction_rate,
    detect_contradictions,
)


def _claim(
    cid: str,
    doc: str,
    *,
    subject: str = "steel",
    prop: str = "yield_strength",
    value: object = None,
    polarity: object = None,
) -> dict:
    """Build one atomic claim dict; ``value`` / ``polarity`` are optional."""
    claim: dict[str, object] = {"id": cid, "subject": subject, "property": prop, "doc_id": doc}
    if value is not None:
        claim["value"] = value
    if polarity is not None:
        claim["polarity"] = polarity
    return claim


def test_divergent_numeric_pair_flagged() -> None:
    # 200 vs 300 -> divergence 100/300 = 0.333 >= 0.30.
    claims = [_claim("a", "doc1", value=200.0), _claim("b", "doc2", value=300.0)]
    pairs = detect_contradictions(claims)
    assert len(pairs) == 1
    assert pairs[0].kind == "numeric"
    assert abs(pairs[0].divergence - 0.3333) < 1e-3
    assert pairs[0].doc_ids == ("doc1", "doc2")


def test_same_doc_pair_not_flagged_self_consistency() -> None:
    # Wildly divergent values, but same document -> never a contradiction.
    claims = [_claim("a", "doc1", value=10.0), _claim("b", "doc1", value=1000.0)]
    assert detect_contradictions(claims) == []


def test_opposite_polarity_flagged() -> None:
    claims = [
        _claim("a", "doc1", prop="causes_cancer", value=None, polarity="supports"),
        _claim("b", "doc2", prop="causes_cancer", value=None, polarity="refutes"),
    ]
    pairs = detect_contradictions(claims)
    assert len(pairs) == 1
    assert pairs[0].kind == "polarity"
    assert pairs[0].divergence == 1.0


def test_bool_polarity_opposition_flagged() -> None:
    claims = [
        _claim("a", "doc1", prop="is_toxic", polarity=True),
        _claim("b", "doc2", prop="is_toxic", polarity=False),
    ]
    pairs = detect_contradictions(claims)
    assert len(pairs) == 1
    assert pairs[0].kind == "polarity"


def test_agreeing_numeric_values_not_flagged() -> None:
    # 100 vs 105 -> divergence 5/105 = 0.048 < 0.30.
    claims = [_claim("a", "doc1", value=100.0), _claim("b", "doc2", value=105.0)]
    assert detect_contradictions(claims) == []


def test_same_polarity_not_flagged() -> None:
    claims = [
        _claim("a", "doc1", prop="causes_cancer", polarity="supports"),
        _claim("b", "doc2", prop="causes_cancer", polarity="positive"),
    ]
    assert detect_contradictions(claims) == []


def test_contradiction_rate_computed() -> None:
    # One flagged pair across two distinct documents -> rate 1/2 = 0.5.
    claims = [_claim("a", "doc1", value=200.0), _claim("b", "doc2", value=300.0)]
    assert contradiction_rate(claims) == 0.5


def test_contradiction_rate_empty_corpus_is_zero() -> None:
    assert contradiction_rate([]) == 0.0


def test_multiple_subjects_isolated() -> None:
    # Divergent values but about DIFFERENT subjects -> no cross-subject pairing.
    claims = [
        _claim("a", "doc1", subject="steel", value=200.0),
        _claim("b", "doc2", subject="aluminium", value=600.0),
    ]
    assert detect_contradictions(claims) == []


def test_different_properties_isolated() -> None:
    # Same subject, divergent values, but DIFFERENT properties -> not paired.
    claims = [
        _claim("a", "doc1", subject="steel", prop="yield_strength", value=200.0),
        _claim("b", "doc2", subject="steel", prop="density", value=600.0),
    ]
    assert detect_contradictions(claims) == []


def test_three_docs_produce_three_pairs() -> None:
    # Three mutually divergent claims across three docs -> C(3,2) = 3 pairs.
    claims = [
        _claim("a", "doc1", value=100.0),
        _claim("b", "doc2", value=200.0),
        _claim("c", "doc3", value=400.0),
    ]
    pairs = detect_contradictions(claims)
    assert len(pairs) == 3
    assert contradiction_rate(claims) == 1.0  # 3 pairs / 3 docs


def test_as_dict_round_trips_all_fields() -> None:
    claims = [_claim("a", "doc1", value=200.0), _claim("b", "doc2", value=300.0)]
    pair = detect_contradictions(claims)[0]
    data = pair.as_dict()
    assert data == {
        "claim_a": "a",
        "claim_b": "b",
        "subject": "steel",
        "kind": "numeric",
        "divergence": pair.divergence,
        "doc_ids": ["doc1", "doc2"],
    }
    # doc_ids must serialize as a plain list, not a tuple.
    assert isinstance(data["doc_ids"], list)


def test_pair_is_frozen() -> None:
    pair = ContradictionPair("a", "b", "steel", "numeric", 0.5, ("doc1", "doc2"))
    try:
        pair.divergence = 0.9  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject mutation
        raise AssertionError("ContradictionPair should be immutable")


def test_module_docstring_cites_paperqa2_arxiv() -> None:
    doc = pqc.__doc__ or ""
    assert "2409.13740" in doc
    assert "PaperQA2" in doc
