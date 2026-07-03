"""Security response headers (§14.12).

Стандартные заголовки безопасности HTTP на чистом stdlib. §14.12 требует
отдавать клиенту защитные заголовки (``X-Content-Type-Options``,
``X-Frame-Options``, ``Referrer-Policy`` и опциональный ``Content-Security-Policy``),
но отдельного модуля для их сборки не было. :class:`SecurityHeaders` —
неизменяемый набор значений с двумя видами сериализации: :meth:`as_dict`
(snake_case поля датакласса) и :meth:`to_headers` (точные имена HTTP-заголовков),
причём ``Content-Security-Policy`` опускается, когда ``csp`` равен ``None``.
:func:`build_security_headers` собирает готовый dict заголовков.

Standard HTTP security headers on the standard library only. §14.12 requires
surfacing protective headers (``X-Content-Type-Options``, ``X-Frame-Options``,
``Referrer-Policy`` and an optional ``Content-Security-Policy``) to the client,
but no module assembled them. :class:`SecurityHeaders` is a frozen value set
with two serialisations: :meth:`as_dict` (snake_case dataclass fields) and
:meth:`to_headers` (the exact HTTP header names), omitting
``Content-Security-Policy`` when ``csp`` is ``None``.
:func:`build_security_headers` assembles the ready header dict.

* :class:`SecurityHeaders`      — frozen carrier for the four header values.
* :meth:`SecurityHeaders.as_dict`    — snake_case field dict.
* :meth:`SecurityHeaders.to_headers` — exact HTTP header-name dict.
* :func:`build_security_headers`     — assemble the header dict from kwargs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SecurityHeaders:
    """Неизменяемый набор защитных заголовков HTTP (§14.12).

    Frozen carrier for the standard security header values. ``csp`` is optional:
    when it is ``None`` the ``Content-Security-Policy`` header is omitted from
    :meth:`to_headers`. :meth:`as_dict` exposes the raw snake_case fields while
    :meth:`to_headers` renders the exact HTTP header names.
    """

    content_type_options: str = "nosniff"
    frame_options: str = "DENY"
    referrer_policy: str = "no-referrer"
    csp: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Обычный dict полей (snake_case) / plain snake_case field dict."""
        return {
            "content_type_options": self.content_type_options,
            "frame_options": self.frame_options,
            "referrer_policy": self.referrer_policy,
            "csp": self.csp,
        }

    def to_headers(self) -> dict[str, str]:
        """Точные имена HTTP-заголовков / exact HTTP header-name dict (§14.12).

        ``Content-Security-Policy`` is included only when :attr:`csp` is set;
        a ``None`` policy leaves the key out entirely.
        """
        headers: dict[str, str] = {
            "X-Content-Type-Options": self.content_type_options,
            "X-Frame-Options": self.frame_options,
            "Referrer-Policy": self.referrer_policy,
        }
        if self.csp is not None:
            headers["Content-Security-Policy"] = self.csp
        return headers


def build_security_headers(
    *,
    csp: str | None = None,
    frame_options: str = "DENY",
) -> dict[str, str]:
    """Собрать dict защитных заголовков (§14.12) / assemble the security header dict.

    Builds a :class:`SecurityHeaders` with the given ``frame_options`` (default
    ``DENY``) and optional ``csp``, then renders it via
    :meth:`SecurityHeaders.to_headers`. ``Content-Security-Policy`` is omitted
    when ``csp`` is ``None``.
    """
    return SecurityHeaders(frame_options=frame_options, csp=csp).to_headers()
