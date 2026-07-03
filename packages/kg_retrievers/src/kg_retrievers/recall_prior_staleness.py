"""Recall-prior staleness detector (§25.10).

Детектор устаревания recall-приоритетов — an ops-side check that flags recall
priors whose ``(parser_version, extractor_version)`` pair no longer matches the
currently-active pipeline versions. Absence outputs (e.g. confidence-of-absence
scores) that lean on a recall prior are only trustworthy while that prior was
measured on the *current* parser/extractor combination; once either component is
upgraded, a prior baked against the old version becomes stale and any absence
claim resting on it should be surfaced for re-measurement.

This is a gap not covered by ``recall_report`` or ``recall_prior_fusion``: those
modules summarise and fuse priors but never compare a prior's provenance against
a declared *current* version, so a silently-outdated prior would flow through
unnoticed.

A prior is a plain dict::

    {"context_key": str, "parser_version": str, "extractor_version": str}

Staleness reasons:

* ``parser_outdated``    — only the parser version differs from current.
* ``extractor_outdated`` — only the extractor version differs from current.
* ``both``               — both versions differ from current.

A prior matching *both* current versions is fresh. The module is pure/in-memory:
it takes plain prior dicts and returns frozen dataclasses, with no graph or I/O
access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Reason: only the parser version is out of date (только парсер устарел).
REASON_PARSER = "parser_outdated"

# Reason: only the extractor version is out of date (только экстрактор устарел).
REASON_EXTRACTOR = "extractor_outdated"

# Reason: both parser and extractor versions are out of date (оба устарели).
REASON_BOTH = "both"


@dataclass(frozen=True)
class StalePrior:
    """A single recall prior flagged as stale, with its reason (§25.10)."""

    context_key: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict view (сериализация) of this stale prior."""
        return {
            "context_key": self.context_key,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StalenessReport:
    """Staleness scan result over a batch of recall priors (§25.10).

    Отчёт об устаревании: the stale priors (with reasons), the ``context_key``s
    of fresh priors, their counts, and the fraction of scanned priors found
    stale (``0.0`` when there are no priors, без деления на ноль).
    """

    stale: list[StalePrior]
    fresh: list[str]
    n_stale: int
    n_fresh: int
    stale_fraction: float

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict view (сериализация) of the staleness report."""
        return {
            "stale": [s.as_dict() for s in self.stale],
            "fresh": list(self.fresh),
            "n_stale": self.n_stale,
            "n_fresh": self.n_fresh,
            "stale_fraction": self.stale_fraction,
        }


def _reason(parser_ok: bool, extractor_ok: bool) -> str | None:
    """Staleness reason for a prior, or ``None`` when it is fresh.

    Причина устаревания: ``None`` if both components match current, otherwise
    ``parser_outdated`` / ``extractor_outdated`` / ``both`` per which differ.
    """
    if parser_ok and extractor_ok:
        return None
    if not parser_ok and not extractor_ok:
        return REASON_BOTH
    if not parser_ok:
        return REASON_PARSER
    return REASON_EXTRACTOR


def find_stale_priors(
    priors: list[dict],
    current_parser_version: str,
    current_extractor_version: str,
) -> StalenessReport:
    """Flag recall priors whose versions no longer match current (§25.10).

    Сравнивает каждый prior с текущими версиями: a prior is fresh only when its
    ``parser_version`` and ``extractor_version`` both equal the current values;
    otherwise it is stale with a reason describing which component(s) drifted.

    :param priors: recall priors, each a dict with ``context_key``,
        ``parser_version`` and ``extractor_version``.
    :param current_parser_version: the currently-active parser version.
    :param current_extractor_version: the currently-active extractor version.
    :returns: a :class:`StalenessReport` with the stale priors, fresh keys,
        counts, and the stale fraction (``0.0`` for an empty input).
    """
    stale: list[StalePrior] = []
    fresh: list[str] = []

    for prior in priors:
        context_key = prior["context_key"]
        parser_ok = prior["parser_version"] == current_parser_version
        extractor_ok = prior["extractor_version"] == current_extractor_version
        reason = _reason(parser_ok, extractor_ok)
        if reason is None:
            fresh.append(context_key)
        else:
            stale.append(StalePrior(context_key=context_key, reason=reason))

    n_stale = len(stale)
    n_fresh = len(fresh)
    total = n_stale + n_fresh
    stale_fraction = (n_stale / total) if total else 0.0

    return StalenessReport(
        stale=stale,
        fresh=fresh,
        n_stale=n_stale,
        n_fresh=n_fresh,
        stale_fraction=stale_fraction,
    )
