"""CORS allowlist policy + preflight header building (§14.12).

Реализует разрешающий список (allowlist) источников (origins) для фронтенда
согласно §14.12: только явно перечисленные origin получают заголовки
``Access-Control-Allow-*``, а preflight-запросы (``OPTIONS``) отклоняются, если
origin не в списке или метод не разрешён. Чистый stdlib, без FastAPI.

Implements the CORS allowlist for the frontend origin required by §14.12: only
explicitly listed origins receive ``Access-Control-Allow-*`` headers, and a
preflight (``OPTIONS``) request is rejected when the origin is not allowlisted
or the requested method is not permitted. Pure standard library, no FastAPI:

* :class:`CorsPolicy`        — frozen allow-lists + credentials/max-age carrier.
* :func:`is_allowed_origin`  — exact-match (or ``*`` wildcard) origin check.
* :func:`preflight_headers`  — ``Access-Control-Allow-*`` dict, or ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Wildcard entry in ``allow_origins`` that matches any origin (§14.12).
_WILDCARD = "*"


@dataclass(frozen=True)
class CorsPolicy:
    """Неизменяемая политика CORS: списки, credentials, max-age (§14.12).

    Frozen carrier for one CORS policy: the allow-listed ``allow_origins`` (an
    exact origin such as ``https://app.example`` or the ``*`` wildcard), the
    permitted ``allow_methods`` and ``allow_headers``, whether credentials are
    allowed (``allow_credentials``) and the preflight cache ``max_age`` seconds.
    """

    allow_origins: tuple[str, ...]
    allow_methods: tuple[str, ...]
    allow_headers: tuple[str, ...]
    allow_credentials: bool
    max_age: int

    def as_dict(self) -> dict[str, object]:
        """Обычный dict полей / plain field dict for logging and assertions."""
        return {
            "allow_origins": list(self.allow_origins),
            "allow_methods": list(self.allow_methods),
            "allow_headers": list(self.allow_headers),
            "allow_credentials": self.allow_credentials,
            "max_age": self.max_age,
        }


def is_allowed_origin(policy: CorsPolicy, origin: str) -> bool:
    """Разрешён ли origin по allowlist (учитывая ``*``) / origin check (§14.12).

    Returns ``True`` when ``origin`` matches an entry in ``policy.allow_origins``
    exactly, or when the wildcard ``*`` is present in the allow-list; otherwise
    ``False`` (an empty allow-list, or an unlisted origin, is rejected).
    """
    if _WILDCARD in policy.allow_origins:
        return True
    return origin in policy.allow_origins


def preflight_headers(
    policy: CorsPolicy,
    origin: str,
    request_method: str,
) -> dict[str, str] | None:
    """Заголовки preflight-ответа или ``None`` / preflight header dict (§14.12).

    Builds the ``Access-Control-Allow-*`` response headers for a CORS preflight
    (``OPTIONS``) request. Returns ``None`` when the ``origin`` is not
    allowlisted (:func:`is_allowed_origin`) or when ``request_method`` (matched
    case-insensitively) is not in ``policy.allow_methods``. Otherwise:

    * ``Access-Control-Allow-Origin``  echoes ``origin``;
    * ``Access-Control-Allow-Methods`` is the comma-joined ``allow_methods``;
    * ``Access-Control-Allow-Headers`` is the comma-joined ``allow_headers``;
    * ``Access-Control-Max-Age``       is ``str(policy.max_age)``;
    * ``Access-Control-Allow-Credentials`` is ``"true"`` only when enabled.
    """
    if not is_allowed_origin(policy, origin):
        return None
    permitted = {method.upper() for method in policy.allow_methods}
    if request_method.upper() not in permitted:
        return None
    headers: dict[str, str] = {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": ", ".join(policy.allow_methods),
        "Access-Control-Allow-Headers": ", ".join(policy.allow_headers),
        "Access-Control-Max-Age": str(policy.max_age),
    }
    if policy.allow_credentials:
        headers["Access-Control-Allow-Credentials"] = "true"
    return headers
