"""Asset staleness / rematerialization — устаревание ассетов (§9.8).

An asset is *stale* when its last materialization is older than any of its
upstream inputs — «ассет устарел, если апстрим новее». A scheduler consults
this before a run to decide which assets need re-materialising, without ever
touching a store or a wall-clock: every timestamp is supplied by the caller.

Freshness is a pure function of two timestamps:

* :func:`newest`      — the most recent upstream timestamp, or ``None`` when
  there are no upstreams («нет апстримов — нет времени»).
* :func:`is_stale`    — ``True`` when the asset was **never materialized**
  (``asset_last is None``) or when **any** upstream is strictly newer than it.
* :func:`stale_assets` — apply the gate across a dependency map, yielding one
  :class:`Staleness` verdict per key with a machine-readable ``reason``.

The three reasons are mutually exclusive:

* ``never_materialized`` — the asset has no recorded materialization.
* ``upstream_newer``     — the asset exists but an upstream is newer.
* ``fresh``              — the asset is at least as new as every upstream.

Everything here is deterministic and side-effect free.

Public API:

* :class:`Staleness`   — frozen verdict with :meth:`Staleness.as_dict`.
* :func:`newest`       — newest upstream timestamp or ``None``.
* :func:`is_stale`     — staleness predicate.
* :func:`stale_assets` — per-key verdicts over a dependency map.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

__all__ = [
    "Staleness",
    "is_stale",
    "newest",
    "stale_assets",
]

_REASON_NEVER = "never_materialized"
_REASON_UPSTREAM = "upstream_newer"
_REASON_FRESH = "fresh"


@dataclass(frozen=True, slots=True)
class Staleness:
    """Immutable staleness verdict — неизменяемый вердикт (§9.8).

    ``asset_key`` names the asset, ``stale`` is the boolean decision and
    ``reason`` is one of ``never_materialized`` / ``upstream_newer`` / ``fresh``.
    """

    asset_key: str
    stale: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — вердикт как словарь (§9.8)."""
        return {
            "asset_key": self.asset_key,
            "stale": self.stale,
            "reason": self.reason,
        }


def newest(upstream_last: Mapping[str, float]) -> float | None:
    """Newest upstream timestamp — самое свежее время апстрима (§9.8).

    Returns the maximum value of ``upstream_last``, or ``None`` when the mapping
    is empty («нет апстримов — нет времени»).
    """
    if not upstream_last:
        return None
    return max(upstream_last.values())


def is_stale(asset_last: float | None, upstream_last: Mapping[str, float]) -> bool:
    """Is the asset stale? — устарел ли ассет? (§9.8).

    ``True`` iff the asset was never materialized (``asset_last is None``) or any
    upstream is strictly newer than ``asset_last``. With no upstreams a
    materialized asset is always fresh.
    """
    if asset_last is None:
        return True
    latest = newest(upstream_last)
    if latest is None:
        return False
    return latest > asset_last


def stale_assets(
    materialized: Mapping[str, float | None],
    deps: Mapping[str, tuple[str, ...]],
) -> list[Staleness]:
    """Per-key staleness verdicts — вердикты устаревания по ключам (§9.8).

    Yields exactly one :class:`Staleness` per key in ``deps``. For each key the
    upstream timestamps are looked up in ``materialized`` (missing / ``None``
    upstreams are ignored — an upstream that was never built cannot be «newer»).
    The ``reason`` is ``never_materialized`` when the asset itself has no
    timestamp, ``upstream_newer`` when a live upstream is newer, else ``fresh``.
    """
    verdicts: list[Staleness] = []
    for key in deps:
        asset_last = materialized.get(key)
        upstream_last: dict[str, float] = {}
        for dep in deps[key]:
            dep_last = materialized.get(dep)
            if dep_last is not None:
                upstream_last[dep] = dep_last

        stale = is_stale(asset_last, upstream_last)
        if not stale:
            reason = _REASON_FRESH
        elif asset_last is None:
            reason = _REASON_NEVER
        else:
            reason = _REASON_UPSTREAM
        verdicts.append(Staleness(asset_key=key, stale=stale, reason=reason))
    return verdicts
