"""Data-retention policy resolver — резолвер политики хранения (§10.11/§10.12).

Every object we persist lands in exactly one *bucket* — a coarse storage class
that says what kind of data it is and, therefore, how long we are obliged (or
allowed) to keep it. The three buckets this module knows about mirror the storage
layout of §10.11:

* ``kg-raw`` — untouched source payloads. Kept for **10 years** (3650 days) and
  archived, because a raw artefact is the ground truth we may need to re-parse.
* ``kg-parsed`` — derived / parsed representations. Kept for **2 years**
  (730 days) and archived; cheaper to regenerate than raw, so a shorter horizon.
* ``kg-audit`` — audit records. Kept for **10 years** (3650 days) but **not**
  archived — audit trails stay hot for the whole retention window.

A :class:`RetentionRule` is a frozen ``(bucket, retention_days, archive)`` triple.
:data:`DEFAULT_RULES` is the built-in policy; every function accepts a ``rules``
override so callers can supply a custom policy (tests, per-tenant overrides)
without touching the default.

Resolver API:

* :func:`rule_for` — bucket → :class:`RetentionRule` (raises :class:`KeyError`).
* :func:`expiry_date` — ``created`` date → date at which retention lapses.
* :func:`is_expired` — is an object past its retention window as of a given day?
* :func:`expired_ids` — filter ``(id, bucket, created)`` rows to the expired ids.

The resolver carries no clock and no I/O — детерминизм: it only maps buckets to
rules and does calendar arithmetic on dates the caller passes in.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from types import MappingProxyType
from typing import Any

__all__ = [
    "RetentionRule",
    "DEFAULT_RULES",
    "rule_for",
    "expiry_date",
    "is_expired",
    "expired_ids",
]


@dataclass(frozen=True, slots=True)
class RetentionRule:
    """Retention rule for one bucket — правило хранения для бакета (§10.11).

    ``retention_days`` is the number of days an object stays *live* counting from
    its creation date; once that many days have elapsed the object has expired and
    is eligible for deletion (or, if ``archive`` is true, for cold archival first).
    """

    bucket: str
    retention_days: int
    archive: bool

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-JSON view — плоское представление для JSON/конфигов."""
        return {
            "bucket": self.bucket,
            "retention_days": self.retention_days,
            "archive": self.archive,
        }


# Built-in policy — встроенная политика (§10.11/§10.12). Frozen into a read-only
# proxy so the shared default cannot be mutated by any caller.
DEFAULT_RULES: Mapping[str, RetentionRule] = MappingProxyType(
    {
        "kg-raw": RetentionRule("kg-raw", 3650, True),
        "kg-parsed": RetentionRule("kg-parsed", 730, True),
        "kg-audit": RetentionRule("kg-audit", 3650, False),
    }
)


def rule_for(
    bucket: str,
    rules: Mapping[str, RetentionRule] = DEFAULT_RULES,
) -> RetentionRule:
    """Resolve ``bucket`` to its rule — раздача правила по бакету (§10.11).

    :raises KeyError: if ``bucket`` is not present in ``rules``.
    """
    return rules[bucket]


def expiry_date(
    created: date,
    bucket: str,
    rules: Mapping[str, RetentionRule] = DEFAULT_RULES,
) -> date:
    """Date at which retention lapses — дата истечения хранения (§10.11).

    The object created on ``created`` in ``bucket`` expires
    ``retention_days`` days later.
    """
    return created + timedelta(days=rule_for(bucket, rules).retention_days)


def is_expired(
    created: date,
    as_of: date,
    bucket: str,
    rules: Mapping[str, RetentionRule] = DEFAULT_RULES,
) -> bool:
    """Has retention passed by ``as_of``? — истёк ли срок к дате (§10.11).

    Returns ``True`` once ``as_of`` reaches or passes the expiry date.
    """
    return as_of >= expiry_date(created, bucket, rules)


def expired_ids(
    items: Iterable[tuple[str, str, date]],
    as_of: date,
    rules: Mapping[str, RetentionRule] = DEFAULT_RULES,
) -> list[str]:
    """Filter ``(id, bucket, created)`` rows to expired ids — фильтр истёкших.

    Each item is a ``(id, bucket, created)`` triple; the returned list holds the
    ids whose retention window has passed as of ``as_of``, preserving input order.
    """
    return [
        item_id for item_id, bucket, created in items if is_expired(created, as_of, bucket, rules)
    ]
