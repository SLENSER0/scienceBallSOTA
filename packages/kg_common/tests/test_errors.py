"""Structured error taxonomy tests (§14.2 ErrorResponse + exception handlers)."""

from __future__ import annotations

from kg_common.errors import (
    INTERNAL_ERROR_CODE,
    INTERNAL_ERROR_MESSAGE,
    AccessDeniedError,
    ConflictError,
    ErrorResponse,
    KgError,
    NotFoundError,
    UpstreamError,
    ValidationError,
    error_taxonomy,
    http_status_for,
    to_error_response,
)

# Hand-checked truth table: exception class -> (http_status, error_code).
EXPECTED = {
    NotFoundError: (404, "not_found"),
    ValidationError: (422, "validation_error"),
    AccessDeniedError: (403, "access_denied"),
    ConflictError: (409, "conflict"),
    UpstreamError: (502, "upstream_error"),
}


def test_each_exception_carries_status_and_code() -> None:
    for cls, (status, code) in EXPECTED.items():
        exc = cls("boom")
        assert exc.http_status == status
        assert exc.error_code == code
        # Both live on the class and the instance (ClassVar).
        assert cls.http_status == status
        assert cls.error_code == code


def test_all_domain_errors_are_kgerror_subclasses() -> None:
    for cls in EXPECTED:
        assert issubclass(cls, KgError)
        assert isinstance(cls("x"), KgError)


def test_base_kgerror_is_internal_500() -> None:
    exc = KgError()
    assert exc.http_status == 500
    assert exc.error_code == "internal_error"
    assert exc.message == "Application error"


def test_default_message_used_when_omitted() -> None:
    assert NotFoundError().message == "Resource not found"
    assert ConflictError().message == "Conflict"
    # Explicit message wins.
    assert NotFoundError("material:al-cu missing").message == "material:al-cu missing"


def test_to_error_response_serialises_camelcase() -> None:
    er = to_error_response(NotFoundError("no such material"))
    assert isinstance(er, ErrorResponse)
    payload = er.model_dump(by_alias=True)
    assert payload["errorCode"] == "not_found"
    assert payload["message"] == "no such material"
    # snake_case must not leak onto the wire.
    assert "error_code" not in payload
    assert "request_id" not in payload
    assert set(payload) == {"errorCode", "message", "detail", "requestId"}


def test_plain_exception_maps_to_internal_error() -> None:
    exc = ValueError("secret internals: db password = hunter2")
    er = to_error_response(exc)
    assert er.error_code == INTERNAL_ERROR_CODE == "internal_error"
    assert http_status_for(exc) == 500
    # Raw exception text is scrubbed — no leak of internals.
    assert er.message == INTERNAL_ERROR_MESSAGE == "Internal server error"
    assert "hunter2" not in er.message
    assert er.detail is None


def test_request_id_threaded_through() -> None:
    er = to_error_response(ConflictError("duplicate alias"), request_id="req-abc-123")
    assert er.request_id == "req-abc-123"
    assert er.model_dump(by_alias=True)["requestId"] == "req-abc-123"
    # Also threaded for the non-KgError branch.
    er2 = to_error_response(RuntimeError("x"), request_id="req-xyz")
    assert er2.request_id == "req-xyz"


def test_detail_preserved_through_to_error_response() -> None:
    exc = ValidationError("bad field", detail={"field": "temperatureC", "op": "range"})
    er = to_error_response(exc)
    assert er.detail == {"field": "temperatureC", "op": "range"}
    assert er.error_code == "validation_error"
    assert er.model_dump(by_alias=True)["detail"] == {"field": "temperatureC", "op": "range"}


def test_http_status_for_all_branches() -> None:
    assert http_status_for(NotFoundError()) == 404
    assert http_status_for(UpstreamError()) == 502
    assert http_status_for(AccessDeniedError()) == 403
    assert http_status_for(KgError()) == 500
    assert http_status_for(TypeError("nope")) == 500


def test_error_response_round_trips_model_validate() -> None:
    original = ErrorResponse(
        error_code="conflict",
        message="duplicate",
        detail={"id": "material:al-cu"},
        request_id="req-1",
    )
    wire = original.model_dump(by_alias=True)
    assert wire["errorCode"] == "conflict"
    rebuilt = ErrorResponse.model_validate(wire)
    assert rebuilt == original
    assert rebuilt.error_code == "conflict"
    assert rebuilt.request_id == "req-1"


def test_error_response_accepts_snake_case_too() -> None:
    # populate_by_name=True: field names also accepted on input.
    er = ErrorResponse.model_validate(
        {"error_code": "not_found", "message": "gone", "request_id": "r9"}
    )
    assert er.error_code == "not_found"
    assert er.request_id == "r9"
    assert er.detail is None


def test_error_taxonomy_covers_all_classes() -> None:
    specs = error_taxonomy()
    by_code = {spec.error_code: spec for spec in specs}
    # Base + five concrete errors; base and non-error share "internal_error".
    assert by_code["not_found"].http_status == 404
    assert by_code["upstream_error"].http_status == 502
    assert by_code["internal_error"].exception is KgError
    # Frozen dataclass structured view.
    assert specs[1].as_dict() == {
        "error_code": "not_found",
        "http_status": 404,
        "exception": "NotFoundError",
    }
