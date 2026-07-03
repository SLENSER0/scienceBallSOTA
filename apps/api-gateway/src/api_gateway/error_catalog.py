"""Extended HTTP error taxonomy + size-limit helper (§14.3).

Расширенный каталог ошибок шлюза, надстроенный над :mod:`kg_common.errors`.
Base §14.2 covers 404/422/403/409/502 via :class:`~kg_common.errors.KgError`;
this module adds the transport-level statuses the gateway also emits —
401 / 403 / 413 / 429 / 503 / 504 — as ready-made builders returning a
``(http_status, ErrorResponse-dict)`` tuple with a *stable* machine code and a
bilingual RU / EN message.

Reuse, not rewrite: the response dict is produced by
:class:`kg_common.errors.ErrorResponse` (same envelope), and
:class:`PayloadTooLarge` subclasses :class:`kg_common.errors.KgError`, so the
existing scrub/serialize path (:func:`~kg_common.errors.to_error_response`)
handles it unchanged.

* :class:`CatalogEntry`   — frozen descriptor (code + status + RU/EN message).
* builders (:func:`unauthorized` … :func:`upstream_timeout`) — envelope tuples.
* :func:`enforce_size`    — raise :class:`PayloadTooLarge` past a byte limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from kg_common.errors import ErrorResponse, KgError


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """Immutable descriptor of one extended-taxonomy error (§14.3).

    Holds a stable machine ``error_code``, the HTTP ``http_status`` and the two
    halves of the bilingual message. :meth:`response` renders the wire envelope;
    :meth:`as_dict` gives a structured view of the descriptor itself.
    """

    error_code: str
    http_status: int
    message_ru: str
    message_en: str

    @property
    def message(self) -> str:
        """Bilingual human message — «RU / EN» (§14.3)."""
        return f"{self.message_ru} / {self.message_en}"

    def response(self, *, detail: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build the :class:`~kg_common.errors.ErrorResponse`-shaped dict (§14.3)."""
        return ErrorResponse(
            error_code=self.error_code,
            message=self.message,
            detail=detail,
        ).model_dump()

    def as_dict(self) -> dict[str, object]:
        """Structured view of this descriptor — таблица расширенных кодов (§14.3)."""
        return {
            "error_code": self.error_code,
            "http_status": self.http_status,
            "message": self.message,
        }


# --- Stable catalog entries (§14.3) --------------------------------------
# Codes are stable identifiers for client logic / i18n; do not rename.

UNAUTHORIZED = CatalogEntry(
    error_code="unauthorized",
    http_status=401,
    message_ru="Требуется аутентификация",
    message_en="Authentication required",
)
FORBIDDEN = CatalogEntry(
    error_code="forbidden",
    http_status=403,
    message_ru="Доступ запрещён",
    message_en="Forbidden",
)
PAYLOAD_TOO_LARGE = CatalogEntry(
    error_code="payload_too_large",
    http_status=413,
    message_ru="Слишком большой размер запроса",
    message_en="Payload too large",
)
RATE_LIMITED = CatalogEntry(
    error_code="rate_limited",
    http_status=429,
    message_ru="Слишком много запросов",
    message_en="Too many requests",
)
SERVICE_UNAVAILABLE = CatalogEntry(
    error_code="service_unavailable",
    http_status=503,
    message_ru="Сервис временно недоступен",
    message_en="Service unavailable",
)
UPSTREAM_TIMEOUT = CatalogEntry(
    error_code="upstream_timeout",
    http_status=504,
    message_ru="Истекло время ожидания вышестоящего сервиса",
    message_en="Upstream timeout",
)

# Ordered extended taxonomy — used for enumeration / uniqueness checks (§14.3).
CATALOG: tuple[CatalogEntry, ...] = (
    UNAUTHORIZED,
    FORBIDDEN,
    PAYLOAD_TOO_LARGE,
    RATE_LIMITED,
    SERVICE_UNAVAILABLE,
    UPSTREAM_TIMEOUT,
)


class PayloadTooLarge(KgError):
    """Request body exceeded the configured size limit — 413 (§14.3).

    Marker exception raised by :func:`enforce_size`; reuses the base
    :class:`~kg_common.errors.KgError` machinery so the gateway scrubs and
    serializes it like any other domain error.
    """

    error_code: ClassVar[str] = PAYLOAD_TOO_LARGE.error_code
    http_status: ClassVar[int] = PAYLOAD_TOO_LARGE.http_status
    default_message: ClassVar[str] = PAYLOAD_TOO_LARGE.message


# --- Builders — each returns (http_status, ErrorResponse-dict) (§14.3) ----


def unauthorized() -> tuple[int, dict[str, Any]]:
    """401 — учётные данные отсутствуют/недействительны (§14.3)."""
    return UNAUTHORIZED.http_status, UNAUTHORIZED.response()


def forbidden() -> tuple[int, dict[str, Any]]:
    """403 — аутентифицирован, но доступ запрещён (§14.3)."""
    return FORBIDDEN.http_status, FORBIDDEN.response()


def payload_too_large(limit: int) -> tuple[int, dict[str, Any]]:
    """413 — тело запроса больше ``limit`` байт (§14.3)."""
    return PAYLOAD_TOO_LARGE.http_status, PAYLOAD_TOO_LARGE.response(
        detail={"limitBytes": limit},
    )


def rate_limited(retry_after: int) -> tuple[int, dict[str, Any]]:
    """429 — превышен лимит частоты; ``retry_after`` в секундах (§14.3)."""
    return RATE_LIMITED.http_status, RATE_LIMITED.response(
        detail={"retryAfter": retry_after},
    )


def service_unavailable(dep: str) -> tuple[int, dict[str, Any]]:
    """503 — зависимость ``dep`` временно недоступна (§14.3)."""
    return SERVICE_UNAVAILABLE.http_status, SERVICE_UNAVAILABLE.response(
        detail={"dependency": dep},
    )


def upstream_timeout() -> tuple[int, dict[str, Any]]:
    """504 — вышестоящий сервис не ответил вовремя (§14.3)."""
    return UPSTREAM_TIMEOUT.http_status, UPSTREAM_TIMEOUT.response()


def enforce_size(content_length: int, limit: int) -> None:
    """Guard a request body against ``limit`` bytes (§14.3).

    A ``content_length`` at or below ``limit`` is a no-op; strictly greater
    raises :class:`PayloadTooLarge` carrying both figures in ``detail`` so the
    client learns the actual size and the cap it exceeded.
    """
    if content_length > limit:
        raise PayloadTooLarge(
            PAYLOAD_TOO_LARGE.message,
            detail={"contentLength": content_length, "limitBytes": limit},
        )
