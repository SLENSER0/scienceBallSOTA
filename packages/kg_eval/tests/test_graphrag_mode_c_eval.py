"""GraphRAG Mode C evaluation metrics tests (§11.13)."""

from __future__ import annotations

from kg_eval.graphrag_mode_c_eval import ModeCMetrics, evaluate_mode_c


def _claim(
    text: str,
    *,
    cited: list[str] | None = None,
    supported: bool = True,
    numeric_ok: bool | None = None,
) -> dict:
    return {
        "text": text,
        "cited_doc_ids": cited or [],
        "supported": supported,
        "numeric_ok": numeric_ok,
    }


def test_citation_precision_three_of_four() -> None:
    claims = [
        _claim("a", cited=["d1"]),
        _claim("b", cited=["d2"]),
        _claim("c", cited=["d3"]),
        _claim("d", cited=[]),  # no citation
    ]
    m = evaluate_mode_c(claims, used_community_ids=[], total_communities=1)
    assert m.citation_precision == 0.75


def test_unsupported_claim_rate_one_of_four() -> None:
    claims = [
        _claim("a", supported=True),
        _claim("b", supported=True),
        _claim("c", supported=True),
        _claim("d", supported=False),  # unsupported
    ]
    m = evaluate_mode_c(claims, used_community_ids=[], total_communities=1)
    assert m.unsupported_claim_rate == 0.25


def test_community_coverage_two_of_five() -> None:
    m = evaluate_mode_c(
        [_claim("a")],
        used_community_ids=["c1", "c2", "c1"],  # dup collapses to 2 unique
        total_communities=5,
    )
    assert m.community_coverage == 0.4


def test_community_coverage_zero_total_no_zerodiv() -> None:
    m = evaluate_mode_c(
        [_claim("a")],
        used_community_ids=["c1"],
        total_communities=0,
    )
    assert m.community_coverage == 0.0


def test_numeric_accuracy_one_wrong_of_two() -> None:
    claims = [
        _claim("n1", numeric_ok=True),
        _claim("n2", numeric_ok=False),
        _claim("prose", numeric_ok=None),  # ignored
    ]
    m = evaluate_mode_c(claims, used_community_ids=[], total_communities=1)
    assert m.numeric_accuracy == 0.5


def test_numeric_accuracy_no_numeric_claims_is_one() -> None:
    claims = [_claim("a"), _claim("b")]  # numeric_ok all None
    m = evaluate_mode_c(claims, used_community_ids=[], total_communities=1)
    assert m.numeric_accuracy == 1.0


def test_all_ratios_in_unit_interval() -> None:
    claims = [
        _claim("a", cited=["d1"], supported=True, numeric_ok=True),
        _claim("b", cited=[], supported=False, numeric_ok=False),
    ]
    m = evaluate_mode_c(claims, used_community_ids=["c1"], total_communities=3)
    for v in m.as_dict().values():
        assert 0.0 <= v <= 1.0


def test_as_dict_returns_four_float_keys() -> None:
    m = evaluate_mode_c([_claim("a")], used_community_ids=["c1"], total_communities=2)
    d = m.as_dict()
    assert set(d) == {
        "citation_precision",
        "unsupported_claim_rate",
        "community_coverage",
        "numeric_accuracy",
    }
    assert all(isinstance(v, float) for v in d.values())


def test_empty_batch_no_zerodiv() -> None:
    m = evaluate_mode_c([], used_community_ids=[], total_communities=4)
    assert m.citation_precision == 0.0
    assert m.unsupported_claim_rate == 0.0
    assert m.numeric_accuracy == 1.0  # vacuously perfect
    assert isinstance(m, ModeCMetrics)
