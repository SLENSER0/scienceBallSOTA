"""Public config / feature-flag projection for ``GET /config`` (§14.15).

Проекция публичной конфигурации шлюза: наружу отдаём только
клиент-безопасные фича-флаги плюс версию/сборку.

``kg_common.feature_flag_parity`` проверяет лишь паритет backend/frontend и
не строит наружную проекцию — этот модуль закрывает пробел на стороне шлюза.

Only allowlisted flags ever reach a client. Non-flag settings (secrets,
internal toggles) are dropped by construction: an absent allowlisted key is
*never* injected, and every emitted value is coerced to ``bool``.

* :data:`PUBLIC_FLAG_ALLOWLIST` — the client-safe flag names.
* :class:`PublicConfig`         — frozen response DTO with :meth:`as_dict`.
* :func:`project_public_flags`  — keep+coerce only allowlisted flags.
* :func:`build_config`          — assemble the ``GET /config`` payload.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Client-safe feature flags exposed via ``GET /config`` (§14.15).
# Клиент-безопасные флаги, отдаваемые наружу.
PUBLIC_FLAG_ALLOWLIST: frozenset[str] = frozenset(
    {
        "enable_graphql_proxy",
        "enable_graphrag",
        "enable_uploads",
        "enable_curation",
    }
)


@dataclass(frozen=True, slots=True)
class PublicConfig:
    """Immutable ``GET /config`` payload (§14.15).

    Неизменяемый ответ ``GET /config``: публичные флаги плюс версия/сборка.

    ``flags`` holds only allowlisted, bool-coerced entries; ``version`` and
    ``build`` identify the running gateway. :meth:`as_dict` renders the wire
    shape ``{flags, version, build}``.
    """

    flags: dict[str, bool]
    version: str
    build: str

    def as_dict(self) -> dict[str, Any]:
        """Return the wire dict — ключи ``{flags, version, build}``."""
        return {
            "flags": dict(self.flags),
            "version": self.version,
            "build": self.build,
        }


def project_public_flags(
    all_flags: Mapping[str, Any],
    allowlist: frozenset[str] = PUBLIC_FLAG_ALLOWLIST,
) -> dict[str, bool]:
    """Project ``all_flags`` down to client-safe, bool-coerced entries (§14.15).

    Оставляем только флаги из allowlist, приводим значения к ``bool``.

    Keeps a key only when it is both present in ``all_flags`` and listed in
    ``allowlist``; an absent allowlisted key is never injected. Non-allowlisted
    keys (secrets, internal toggles) are dropped. Values are coerced via
    ``bool()`` so the output is always a ``dict[str, bool]``.
    """
    return {key: bool(value) for key, value in all_flags.items() if key in allowlist}


def build_config(
    all_flags: Mapping[str, Any],
    version: str,
    build: str,
) -> PublicConfig:
    """Assemble the ``GET /config`` payload from raw flags (§14.15).

    Собираем публичный ответ: проекция флагов + версия/сборка.
    """
    return PublicConfig(
        flags=project_public_flags(all_flags),
        version=version,
        build=build,
    )
