"""Structured error taxonomy — единый конверт ошибок API (§14.2).

Defines the wire-facing :class:`ErrorResponse` envelope and the application
exception hierarchy rooted at :class:`KgError`. Every domain error carries a
*stable* ``error_code`` string and an HTTP ``http_status`` so the gateway can
map an exception to a response without leaking internal stack traces
(«не раскрывая внутренние стектрейсы», §14.2).

Codes are stable identifiers (RU/EN neutral) meant for клиентскую логику and
i18n on the frontend; ``message`` is human-readable. Unknown / non-``KgError``
exceptions are scrubbed to ``internal_error`` / ``500`` so raw exception text
never reaches the client.

* :class:`ErrorResponse`   — Pydantic DTO, camelCase on the wire (``errorCode``).
* :class:`KgError` + subs  — taxonomy: 404 / 422 / 403 / 409 / 502.
* :func:`to_error_response` — build an :class:`ErrorResponse` from any exception.
* :func:`http_status_for`   — HTTP status for any exception (500 fallback).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from kg_common.dto import CamelModel

# Fallback identifiers for anything that is not a ``KgError`` (§14.2).
INTERNAL_ERROR_CODE = "internal_error"
INTERNAL_HTTP_STATUS = 500
# Scrubbed message for unknown errors — deliberately generic (no leak).
INTERNAL_ERROR_MESSAGE = "Internal server error"


class ErrorResponse(CamelModel):
    """Structured error envelope returned by every API error (§14.2).

    Serialized as camelCase (``errorCode`` / ``requestId``) to match the
    frontend TypeScript contract, while Python uses snake_case fields.
    """

    error_code: str
    message: str
    detail: dict[str, Any] | None = None
    request_id: str | None = None


class KgError(Exception):
    """Base application error carrying a stable code + HTTP status (§14.2).

    Subclasses override :attr:`error_code` / :attr:`http_status`. The base
    itself maps to ``internal_error`` / ``500`` — the same fate as any
    non-``KgError`` exception.
    """

    error_code: ClassVar[str] = INTERNAL_ERROR_CODE
    http_status: ClassVar[int] = INTERNAL_HTTP_STATUS
    default_message: ClassVar[str] = "Application error"

    def __init__(
        self,
        message: str | None = None,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.message: str = message if message is not None else self.default_message
        self.detail: dict[str, Any] | None = detail
        super().__init__(self.message)


class NotFoundError(KgError):
    """Requested resource does not exist — ресурс не найден (404, §14.2)."""

    error_code: ClassVar[str] = "not_found"
    http_status: ClassVar[int] = 404
    default_message: ClassVar[str] = "Resource not found"


class ValidationError(KgError):
    """Input failed validation — ошибка валидации (422, §14.2).

    Distinct from :class:`pydantic.ValidationError`; this is the domain-level
    error surfaced to the client.
    """

    error_code: ClassVar[str] = "validation_error"
    http_status: ClassVar[int] = 422
    default_message: ClassVar[str] = "Validation failed"


class AccessDeniedError(KgError):
    """Caller lacks permission — доступ запрещён (403, §14.2)."""

    error_code: ClassVar[str] = "access_denied"
    http_status: ClassVar[int] = 403
    default_message: ClassVar[str] = "Access denied"


class ConflictError(KgError):
    """State conflict, e.g. duplicate — конфликт состояния (409, §14.2)."""

    error_code: ClassVar[str] = "conflict"
    http_status: ClassVar[int] = 409
    default_message: ClassVar[str] = "Conflict"


class UpstreamError(KgError):
    """Upstream/downstream service failed — ошибка вышестоящего сервиса (502, §14.2).

    Used when ``agent`` / ``graph`` / ``search`` / ``ingestion`` return 5xx or
    time out; the raw upstream error is not propagated.
    """

    error_code: ClassVar[str] = "upstream_error"
    http_status: ClassVar[int] = 502
    default_message: ClassVar[str] = "Upstream service error"


# Ordered taxonomy — the base first, then the specific 4xx/5xx errors (§14.2).
KG_ERROR_CLASSES: tuple[type[KgError], ...] = (
    KgError,
    NotFoundError,
    ValidationError,
    AccessDeniedError,
    ConflictError,
    UpstreamError,
)


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    """Immutable descriptor of one error class in the taxonomy (§14.2)."""

    error_code: str
    http_status: int
    exception: type[KgError]

    def as_dict(self) -> dict[str, object]:
        """Structured, JSON-friendly view — таблица кодов ошибок."""
        return {
            "error_code": self.error_code,
            "http_status": self.http_status,
            "exception": self.exception.__name__,
        }


def error_taxonomy() -> tuple[ErrorSpec, ...]:
    """Return the stable code table for every :class:`KgError` class (§14.2)."""
    return tuple(
        ErrorSpec(
            error_code=cls.error_code,
            http_status=cls.http_status,
            exception=cls,
        )
        for cls in KG_ERROR_CLASSES
    )


def http_status_for(exc: BaseException) -> int:
    """HTTP status for any exception; non-``KgError`` falls back to 500 (§14.2)."""
    if isinstance(exc, KgError):
        return exc.http_status
    return INTERNAL_HTTP_STATUS


def to_error_response(
    exc: BaseException,
    request_id: str | None = None,
) -> ErrorResponse:
    """Build an :class:`ErrorResponse` from any exception (§14.2).

    ``KgError`` instances contribute their stable code, message and optional
    ``detail``. Any other exception is scrubbed to ``internal_error`` / a
    generic message so raw internals never reach the client. ``request_id`` is
    threaded through unchanged for correlation (X-Request-ID, §14.2).
    """
    if isinstance(exc, KgError):
        return ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            detail=exc.detail,
            request_id=request_id,
        )
    return ErrorResponse(
        error_code=INTERNAL_ERROR_CODE,
        message=INTERNAL_ERROR_MESSAGE,
        detail=None,
        request_id=request_id,
    )
