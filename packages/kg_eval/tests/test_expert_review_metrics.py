"""Tests for the domain-expert validation loop metrics (§23.22)."""

from __future__ import annotations

import pytest

from kg_eval.expert_review_metrics import ExpertReviewReport, aggregate


def _review(
    rid: str,
    verdict: str,
    time_s: float = 0.0,
    clicks: float = 0.0,
) -> dict[str, object]:
    return {
        "id": rid,
        "verdict": verdict,
        "time_to_evidence_s": time_s,
        "clicks_to_verify": clicks,
    }


def test_empty_is_all_zero() -> None:
    """Пустой вход -> нули и пустой кортеж. / Empty input: zero rates and medians."""
    report = aggregate([])
    assert report.n_reviews == 0
    assert report.useful_rate == 0.0
    assert report.trust_rate == 0.0
    assert report.median_time_to_evidence_s == 0.0
    assert report.median_clicks_to_verify == 0.0
    assert report.error_review_ids == ()


def test_useful_rate_three_of_four() -> None:
    """3 полезных из 4 -> useful_rate==0.75. / 3 useful out of 4 gives 0.75."""
    reviews = [
        _review("a", "useful"),
        _review("b", "trustworthy"),
        _review("c", "useful"),
        _review("d", "wrong_number"),
    ]
    report = aggregate(reviews)
    assert report.n_reviews == 4
    assert report.useful_rate == 0.75


def test_median_time_lower_middle_even_count() -> None:
    """[1,2,3,4] -> нижняя середина == 2.0 (не 2.5). / Even count: lower-middle 2.0."""
    reviews = [
        _review("a", "useful", time_s=1.0),
        _review("b", "useful", time_s=2.0),
        _review("c", "useful", time_s=3.0),
        _review("d", "useful", time_s=4.0),
    ]
    report = aggregate(reviews)
    assert report.median_time_to_evidence_s == 2.0


def test_median_clicks_odd_count() -> None:
    """[2,2,10] -> медиана == 2.0. / Odd count median is the central 2.0."""
    reviews = [
        _review("a", "useful", clicks=2.0),
        _review("b", "useful", clicks=2.0),
        _review("c", "useful", clicks=10.0),
    ]
    report = aggregate(reviews)
    assert report.median_clicks_to_verify == 2.0


def test_error_ids_sorted_tuple_of_both_flags() -> None:
    """Два флага ошибок -> отсортированный кортеж id. / Both error flags collected sorted."""
    reviews = [
        _review("z9", "missing_evidence"),
        _review("useful1", "useful"),
        _review("a1", "wrong_number"),
    ]
    report = aggregate(reviews)
    assert report.error_review_ids == ("a1", "z9")


def test_trust_rate_counts_trustworthy_separately() -> None:
    """trust_rate считает только 'trustworthy'. / trust_rate is trustworthy-only."""
    reviews = [
        _review("a", "useful"),
        _review("b", "trustworthy"),
        _review("c", "trustworthy"),
        _review("d", "wrong_number"),
    ]
    report = aggregate(reviews)
    # 3/4 useful (useful + 2 trustworthy), but only 2/4 trustworthy.
    assert report.useful_rate == 0.75
    assert report.trust_rate == 0.5


def test_as_dict_round_trips_all_six_fields() -> None:
    """as_dict() отдаёт шесть полей с округлением до 4 знаков. / Six fields, 4 dp."""
    reviews = [
        _review("a", "useful", time_s=1.0, clicks=2.0),
        _review("b", "trustworthy", time_s=2.0, clicks=2.0),
        _review("c", "wrong_number", time_s=3.0, clicks=10.0),
    ]
    report = aggregate(reviews)
    data = report.as_dict()
    assert set(data) == {
        "n_reviews",
        "useful_rate",
        "trust_rate",
        "median_time_to_evidence_s",
        "median_clicks_to_verify",
        "error_review_ids",
    }
    assert data["n_reviews"] == 3
    assert data["useful_rate"] == round(2 / 3, 4)
    assert data["trust_rate"] == round(1 / 3, 4)
    assert data["median_time_to_evidence_s"] == 2.0
    assert data["median_clicks_to_verify"] == 2.0
    assert data["error_review_ids"] == ["c"]


def test_report_is_frozen() -> None:
    """Отчёт неизменяем. / Report dataclass is frozen."""
    report = aggregate([_review("a", "useful")])
    assert isinstance(report, ExpertReviewReport)
    with pytest.raises(AttributeError):
        report.useful_rate = 0.0  # type: ignore[misc]
