"""Тесты заголовков безопасности (§14.12) / security-header tests.

Проверяют точную сериализацию :class:`SecurityHeaders` в HTTP-заголовки,
опциональный ``Content-Security-Policy`` и переопределение ``X-Frame-Options``
через :func:`build_security_headers`.
"""

from __future__ import annotations

from api_gateway.security_headers import SecurityHeaders, build_security_headers


def test_content_type_options_nosniff() -> None:
    """(1) to_headers() отдаёт X-Content-Type-Options: nosniff по умолчанию."""
    assert SecurityHeaders().to_headers()["X-Content-Type-Options"] == "nosniff"


def test_default_frame_options_deny() -> None:
    """(2) Дефолтный frame_options рендерится как X-Frame-Options: DENY."""
    assert SecurityHeaders().to_headers()["X-Frame-Options"] == "DENY"


def test_referrer_policy_default_present() -> None:
    """(3) Referrer-Policy: no-referrer присутствует по умолчанию."""
    headers = SecurityHeaders().to_headers()
    assert headers["Referrer-Policy"] == "no-referrer"


def test_csp_none_omits_header() -> None:
    """(4) csp=None → ключа Content-Security-Policy нет."""
    headers = SecurityHeaders(csp=None).to_headers()
    assert "Content-Security-Policy" not in headers


def test_csp_value_present() -> None:
    """(5) csp="default-src 'self'" → значение заголовка присутствует."""
    headers = SecurityHeaders(csp="default-src 'self'").to_headers()
    assert headers["Content-Security-Policy"] == "default-src 'self'"


def test_build_overrides_frame_options() -> None:
    """(6) build_security_headers(frame_options='SAMEORIGIN') переопределяет."""
    headers = build_security_headers(frame_options="SAMEORIGIN")
    assert headers["X-Frame-Options"] == "SAMEORIGIN"


def test_as_dict_snake_case_vs_http_names() -> None:
    """(7) as_dict() — snake_case поля, to_headers() — имена HTTP-заголовков."""
    sec = SecurityHeaders(csp="default-src 'self'")
    d = sec.as_dict()
    assert d == {
        "content_type_options": "nosniff",
        "frame_options": "DENY",
        "referrer_policy": "no-referrer",
        "csp": "default-src 'self'",
    }
    headers = sec.to_headers()
    # HTTP header names, not snake_case fields.
    assert set(headers) == {
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Content-Security-Policy",
    }
    # snake_case keys must NOT leak into the header dict.
    assert not set(d) & set(headers)


def test_build_default_omits_csp() -> None:
    """build_security_headers() без csp опускает Content-Security-Policy."""
    headers = build_security_headers()
    assert "Content-Security-Policy" not in headers
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
