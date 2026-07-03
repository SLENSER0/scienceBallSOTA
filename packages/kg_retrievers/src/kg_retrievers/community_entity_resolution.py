"""§11.5 — GraphRAG entity -> canonical graph id resolution (pure mapper).

GraphRAG community reports name entities as raw text (напр. ``"Iron"``, ``" STEEL "``),
but community payloads need каноническими id графа. This module is a **pure** mapper:
given raw entity names and an alias map (raw-name -> canonical id), it resolves each
name to a canonical id, leaving несопоставленные names as raw text with a ``matched``
flag set to ``False``.

Design note (§11.5): ``community_payload`` reads a store and deliberately does **not**
do name->id alias resolution — that belongs here so the two concerns stay separate. Both
the names and the alias-map keys are normalized via ``casefold`` + ``strip`` before
lookup, so ``" STEEL "`` matches an alias key of ``"steel"``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


def _normalize(name: str) -> str:
    """Normalize a raw name / alias key for lookup: strip whitespace + casefold."""
    return name.strip().casefold()


@dataclass(frozen=True)
class ResolvedEntity:
    """One raw GraphRAG entity name resolved (or not) to a canonical graph id.

    ``raw`` is the original name as it appeared in the community report. ``canonical_id``
    is the graph id it resolved to, or ``None`` when unmatched. ``matched`` mirrors that:
    ``True`` iff ``canonical_id is not None``.
    """

    raw: str
    canonical_id: str | None
    matched: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "canonical_id": self.canonical_id,
            "matched": self.matched,
        }


@dataclass(frozen=True)
class ResolutionResult:
    """The full resolution of a community's raw entity names.

    ``entries`` preserves input order (and duplicates); ``match_rate`` is the fraction
    of names that resolved to a canonical id, in ``[0, 1]`` (``0.0`` on empty input).
    """

    entries: tuple[ResolvedEntity, ...]
    match_rate: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "entries": [e.as_dict() for e in self.entries],
            "match_rate": self.match_rate,
        }


def resolve_entities(
    raw_names: Sequence[str],
    alias_map: Mapping[str, str],
) -> ResolutionResult:
    """Resolve raw GraphRAG entity names to canonical graph ids (§11.5).

    Each name in ``raw_names`` and each key in ``alias_map`` is normalized via
    :func:`_normalize` (``strip`` + ``casefold``) before lookup. Unmatched names yield
    ``canonical_id=None`` and ``matched=False``; the ``raw`` field always preserves the
    original (un-normalized) name so downstream callers can keep it as raw text.

    Duplicate raw names each resolve independently (одинаковый result each time).
    ``match_rate`` = matched / len(raw_names), or ``0.0`` when ``raw_names`` is empty.
    """
    # Normalize alias keys once; last write wins on key collisions after normalization.
    normalized_aliases = {_normalize(k): v for k, v in alias_map.items()}

    entries: list[ResolvedEntity] = []
    matched_count = 0
    for name in raw_names:
        canonical_id = normalized_aliases.get(_normalize(name))
        matched = canonical_id is not None
        if matched:
            matched_count += 1
        entries.append(ResolvedEntity(raw=name, canonical_id=canonical_id, matched=matched))

    total = len(entries)
    match_rate = (matched_count / total) if total else 0.0
    return ResolutionResult(entries=tuple(entries), match_rate=match_rate)
