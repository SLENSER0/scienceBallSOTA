"""Tests for §14.7 search-request range validation.

Проверяют значение ``top_k`` по умолчанию и явное, отклонение ``top_k`` вне
``1..MAX_TOP_K``, пустой ``query``, ``min_confidence`` вне ``[0, 1]``, разбор и
отклонение гибридных ``weights`` и сериализацию через ``as_dict``.

Exercise the default/explicit ``top_k``, out-of-range ``top_k``, empty
``query``, out-of-range ``min_confidence``, hybrid ``weights`` parsing and
rejection, and ``as_dict`` serialization.
"""

from __future__ import annotations

import pytest
from api_gateway.search_request_validation import (
    MAX_TOP_K,
    SearchValidationError,
    ValidatedSearchRequest,
    validate_search_request,
)


def test_top_k_defaults_to_ten() -> None:
    """(1) Missing ``top_k`` defaults to 10."""
    assert validate_search_request({"query": "x"}).top_k == 10


def test_top_k_explicit_is_kept() -> None:
    """(2) An in-range explicit ``top_k`` is preserved."""
    assert validate_search_request({"query": "x", "top_k": 50}).top_k == 50


def test_top_k_zero_rejected() -> None:
    """(3) ``top_k`` of 0 is below the 1 floor and rejected."""
    with pytest.raises(SearchValidationError):
        validate_search_request({"query": "x", "top_k": 0})


def test_top_k_above_max_rejected() -> None:
    """(4) ``top_k`` above MAX_TOP_K is rejected."""
    assert MAX_TOP_K == 200
    with pytest.raises(SearchValidationError):
        validate_search_request({"query": "x", "top_k": 1000})


def test_max_top_k_is_accepted_boundary() -> None:
    """(5) Exactly MAX_TOP_K is the inclusive upper boundary."""
    assert validate_search_request({"query": "x", "top_k": MAX_TOP_K}).top_k == 200


def test_empty_query_rejected() -> None:
    """(6) An empty ``query`` string is rejected."""
    with pytest.raises(SearchValidationError):
        validate_search_request({"query": ""})


def test_whitespace_query_rejected() -> None:
    """(7) A whitespace-only ``query`` is rejected."""
    with pytest.raises(SearchValidationError):
        validate_search_request({"query": "   "})


def test_min_confidence_above_one_rejected() -> None:
    """(8) ``min_confidence`` above 1 is rejected."""
    with pytest.raises(SearchValidationError):
        validate_search_request({"query": "x", "min_confidence": 1.5})


def test_min_confidence_in_range_kept() -> None:
    """(9) An in-range ``min_confidence`` is preserved; absent stays ``None``."""
    assert validate_search_request({"query": "x", "min_confidence": 0.5}).min_confidence == 0.5
    assert validate_search_request({"query": "x"}).min_confidence is None


def test_weights_parsed() -> None:
    """(10) Hybrid ``weights`` are parsed into a float mapping."""
    req = validate_search_request({"query": "x", "weights": {"keyword": 0.7, "vector": 0.3}})
    assert req.weights["keyword"] == 0.7
    assert req.weights["vector"] == 0.3


def test_negative_weight_rejected() -> None:
    """(11) A negative weight is rejected."""
    with pytest.raises(SearchValidationError):
        validate_search_request({"query": "x", "weights": {"keyword": -1}})


def test_zero_sum_weights_rejected() -> None:
    """(12) Non-empty weights that sum to zero are rejected."""
    with pytest.raises(SearchValidationError):
        validate_search_request({"query": "x", "weights": {"keyword": 0, "vector": 0}})


def test_as_dict_round_trips_query() -> None:
    """(13) ``as_dict`` exposes ``query`` and omits ``None`` ``min_confidence``."""
    out = validate_search_request({"query": "x"}).as_dict()
    assert out["query"] == "x"
    assert "min_confidence" not in out


def test_as_dict_includes_min_confidence_when_present() -> None:
    """(14) ``as_dict`` includes ``min_confidence`` when it was supplied."""
    out = validate_search_request({"query": "x", "min_confidence": 0.25}).as_dict()
    assert out["min_confidence"] == 0.25
    assert isinstance(out["weights"], dict)


def test_bool_top_k_rejected() -> None:
    """(15) A bool ``top_k`` (int subclass) is not a valid integer."""
    with pytest.raises(SearchValidationError):
        validate_search_request({"query": "x", "top_k": True})


def test_frozen_request_is_immutable() -> None:
    """(16) ValidatedSearchRequest is frozen."""
    req = validate_search_request({"query": "x"})
    assert isinstance(req, ValidatedSearchRequest)
    with pytest.raises(AttributeError):
        req.top_k = 5  # type: ignore[misc]
