"""Per-role rate-limit configuration — конфигурация лимитов по ролям (§19.13).

The token bucket (:class:`kg_common.ratelimit.TokenBucket`, §19.8) describes *how
fast* a single client may act; it says nothing about *who* the client is. In a
multi-tenant service different roles deserve different budgets — an ``admin`` or
service account may act far more often than an anonymous ``guest``. This module
adds that policy layer on top of the bucket without touching the limiter itself.

:class:`RateLimitConfig` is a frozen mapping from *role* → :class:`TokenBucket`
plus a single ``default`` bucket used for any role that has no explicit entry.
:meth:`~RateLimitConfig.bucket_for` resolves a role to its bucket (falling back to
``default``); :meth:`~RateLimitConfig.as_dict` /
:meth:`~RateLimitConfig.from_dict` round-trip the whole policy through plain JSON
so it can live in config files or be shipped over the wire.

Design goals:

* **Frozen policy, no clock** — детерминизм. The config carries no mutable state
  and never reads a clock; it only *selects* which bucket a limiter should use.
* **Buckets reused, not reinvented** — we import :class:`TokenBucket` and reuse
  its validation and :meth:`~TokenBucket.as_dict`; this module never redefines
  bucket arithmetic.

Public API:

* :class:`RateLimitConfig` — frozen ``{per_role, default}`` policy with
  :meth:`~RateLimitConfig.bucket_for`, :meth:`~RateLimitConfig.as_dict`,
  :meth:`~RateLimitConfig.from_dict`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from kg_common.ratelimit import TokenBucket

__all__ = [
    "RateLimitConfig",
]


@dataclass(frozen=True, slots=True)
class RateLimitConfig:
    """Per-role rate-limit policy — политика лимитов по ролям (§19.13).

    ``per_role`` maps a role name (e.g. ``"admin"``, ``"guest"``) to the
    :class:`TokenBucket` that governs clients of that role; ``default`` is the
    bucket returned for any role absent from ``per_role``. The mapping is copied
    into an immutable :class:`~types.MappingProxyType` on construction so the
    frozen config cannot be mutated after the fact.
    """

    default: TokenBucket
    per_role: Mapping[str, TokenBucket] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Freeze the incoming mapping into a read-only proxy of a private copy so
        # the config is genuinely immutable even if the caller keeps the original.
        object.__setattr__(self, "per_role", MappingProxyType(dict(self.per_role)))

    def bucket_for(self, role: str) -> TokenBucket:
        """Bucket governing ``role`` — ведро для роли (§19.13).

        Returns the explicit :class:`TokenBucket` for ``role`` when one is defined
        in ``per_role``, otherwise the shared ``default`` bucket. An unknown role
        therefore always yields a usable bucket rather than raising.
        """
        return self.per_role.get(role, self.default)

    def as_dict(self) -> dict[str, Any]:
        """Structured, JSON-friendly view — таблица политики (§19.13).

        Both ``default`` and every per-role bucket are rendered via
        :meth:`TokenBucket.as_dict`, so the result is plain nested dicts/floats
        suitable for JSON and consumed back by :meth:`from_dict`.
        """
        return {
            "default": self.default.as_dict(),
            "per_role": {role: bucket.as_dict() for role, bucket in self.per_role.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RateLimitConfig:
        """Rebuild a config from :meth:`as_dict` output — из словаря (§19.13).

        Reads the ``default`` bucket and each ``per_role`` bucket back through
        :class:`TokenBucket`, inheriting its validation (``capacity > 0`` etc.).
        A missing or empty ``per_role`` yields a config with only the default.
        """
        default = _bucket_from(data["default"])
        per_role_raw: Mapping[str, Any] = data.get("per_role") or {}
        per_role = {role: _bucket_from(spec) for role, spec in per_role_raw.items()}
        return cls(default=default, per_role=per_role)


def _bucket_from(spec: Mapping[str, Any]) -> TokenBucket:
    """Build a :class:`TokenBucket` from a ``{capacity, refill_per_sec}`` spec."""
    return TokenBucket(
        capacity=float(spec["capacity"]),
        refill_per_sec=float(spec["refill_per_sec"]),
    )
