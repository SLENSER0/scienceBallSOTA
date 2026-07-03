"""HTTP security headers builder — построитель заголовков безопасности HTTP (§19.7).

Provides a frozen ``SecurityHeaderPolicy`` and ``build_headers`` to emit hardened
transport/response headers (HSTS, frame options, CSP, referrer policy).
Замороженная политика заголовков безопасности и функция сборки заголовков ответа.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class SecurityHeaderPolicy:
    """Immutable security-header policy — неизменяемая политика заголовков (§19.7).

    Attributes:
        hsts_max_age: HSTS ``max-age`` in seconds — срок действия HSTS в секундах.
        enable_hsts: Emit ``Strict-Transport-Security`` when ``True`` — включить HSTS.
        frame_options: ``X-Frame-Options`` value — значение X-Frame-Options.
        content_type_options: Emit ``X-Content-Type-Options: nosniff`` — запрет sniff.
        csp: ``Content-Security-Policy`` value — политика безопасности контента.
        referrer_policy: ``Referrer-Policy`` value — политика реферера.
    """

    hsts_max_age: int = 31536000
    enable_hsts: bool = True
    frame_options: str = "DENY"
    content_type_options: bool = True
    csp: str = "default-src 'self'"
    referrer_policy: str = "no-referrer"

    def as_dict(self) -> dict[str, object]:
        """Return the policy as a plain dict — вернуть политику как словарь (§19.7)."""
        return asdict(self)


def build_headers(policy: SecurityHeaderPolicy) -> dict[str, str]:
    """Build response headers from a policy — собрать заголовки ответа из политики (§19.7).

    Args:
        policy: Source security-header policy — исходная политика заголовков.

    Returns:
        Mapping of header name to value — отображение имени заголовка на значение.
    """
    headers: dict[str, str] = {}
    if policy.enable_hsts:
        headers["Strict-Transport-Security"] = f"max-age={policy.hsts_max_age}; includeSubDomains"
    headers["X-Frame-Options"] = policy.frame_options
    if policy.content_type_options:
        headers["X-Content-Type-Options"] = "nosniff"
    headers["Content-Security-Policy"] = policy.csp
    headers["Referrer-Policy"] = policy.referrer_policy
    return headers
