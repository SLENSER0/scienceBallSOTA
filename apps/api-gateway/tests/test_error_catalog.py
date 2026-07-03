"""Tests for the extended HTTP error taxonomy + size guard (§14.3).

Hermetic and dependency-free. Every builder is checked for its exact HTTP
status, its stable machine code and a non-empty bilingual message; the two
detail-carrying builders (:func:`rate_limited`, :func:`service_unavailable`)
and :func:`payload_too_large` are checked for their payload; codes are asserted
unique across builders; the response dict is asserted to match the
:class:`kg_common.errors.ErrorResponse` field set; and :func:`enforce_size` is
exercised on both sides of the limit (and exactly at it).
"""

from __future__ import annotations

import pytest
from api_gateway.error_catalog import (
    CATALOG,
    PayloadTooLarge,
    enforce_size,
    forbidden,
    payload_too_large,
    rate_limited,
    service_unavailable,
    unauthorized,
    upstream_timeout,
)

from kg_common.errors import ErrorResponse, KgError

# Every zero-arg / trivially-callable builder with its expected (status, code).
_EXPECTED: list[tuple[int, str, tuple[int, dict[str, object]]]] = [
    (401, "unauthorized", unauthorized()),
    (403, "forbidden", forbidden()),
    (413, "payload_too_large", payload_too_large(1024)),
    (429, "rate_limited", rate_limited(30)),
    (503, "service_unavailable", service_unavailable("neo4j")),
    (504, "upstream_timeout", upstream_timeout()),
]


def test_unauthorized_status_code_and_message() -> None:
    status, resp = unauthorized()
    assert status == 401
    assert resp["error_code"] == "unauthorized"
    assert resp["message"] and isinstance(resp["message"], str)


def test_forbidden_status_code_and_message() -> None:
    status, resp = forbidden()
    assert status == 403
    assert resp["error_code"] == "forbidden"
    assert resp["message"]


def test_payload_too_large_status_and_limit_detail() -> None:
    status, resp = payload_too_large(2048)
    assert status == 413
    assert resp["error_code"] == "payload_too_large"
    assert resp["message"]
    assert resp["detail"] == {"limitBytes": 2048}


def test_rate_limited_carries_retry_after() -> None:
    status, resp = rate_limited(45)
    assert status == 429
    assert resp["error_code"] == "rate_limited"
    assert resp["detail"]["retryAfter"] == 45


def test_service_unavailable_carries_dependency() -> None:
    status, resp = service_unavailable("qdrant")
    assert status == 503
    assert resp["error_code"] == "service_unavailable"
    assert resp["detail"]["dependency"] == "qdrant"


def test_upstream_timeout_status_and_message() -> None:
    status, resp = upstream_timeout()
    assert status == 504
    assert resp["error_code"] == "upstream_timeout"
    assert resp["message"]


@pytest.mark.parametrize("status, code, built", _EXPECTED)
def test_builder_status_code_and_nonempty_message(
    status: int, code: str, built: tuple[int, dict[str, object]]
) -> None:
    got_status, resp = built
    assert got_status == status
    assert resp["error_code"] == code
    assert isinstance(resp["message"], str) and resp["message"].strip()


def test_codes_unique_across_builders() -> None:
    codes = [resp["error_code"] for _status, _code, (_s, resp) in _EXPECTED]
    assert len(codes) == len(set(codes)) == 6


def test_statuses_are_the_extended_taxonomy() -> None:
    statuses = {status for status, _code, _built in _EXPECTED}
    assert statuses == {401, 403, 413, 429, 503, 504}


def test_response_shape_matches_kg_common_error_response() -> None:
    _status, resp = unauthorized()
    assert set(resp.keys()) == set(ErrorResponse.model_fields)
    # The dict must round-trip back through the canonical envelope.
    rebuilt = ErrorResponse(**resp)
    assert rebuilt.error_code == "unauthorized"


def test_messages_are_bilingual_ru_en() -> None:
    for _status, _code, (_s, resp) in _EXPECTED:
        msg = resp["message"]
        assert " / " in msg
        assert any("Ѐ" <= ch <= "ӿ" for ch in msg)  # Cyrillic present


def test_catalog_covers_all_six_entries() -> None:
    assert len(CATALOG) == 6
    assert {e.error_code for e in CATALOG} == {
        "unauthorized",
        "forbidden",
        "payload_too_large",
        "rate_limited",
        "service_unavailable",
        "upstream_timeout",
    }


def test_catalog_entry_as_dict_view() -> None:
    entry = next(e for e in CATALOG if e.error_code == "rate_limited")
    assert entry.as_dict() == {
        "error_code": "rate_limited",
        "http_status": 429,
        "message": entry.message,
    }


def test_enforce_size_passes_under_limit() -> None:
    assert enforce_size(500, 1024) is None


def test_enforce_size_passes_at_limit_boundary() -> None:
    assert enforce_size(1024, 1024) is None


def test_enforce_size_raises_over_limit() -> None:
    with pytest.raises(PayloadTooLarge) as exc_info:
        enforce_size(2000, 1024)
    err = exc_info.value
    assert err.http_status == 413
    assert err.error_code == "payload_too_large"
    assert err.detail == {"contentLength": 2000, "limitBytes": 1024}


def test_payload_too_large_marker_is_kg_error() -> None:
    assert issubclass(PayloadTooLarge, KgError)
