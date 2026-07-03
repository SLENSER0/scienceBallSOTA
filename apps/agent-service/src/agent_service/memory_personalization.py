"""§13.20 персонализация запроса из Store / personalization read from long-term Store.

This module is the *read/apply* side of §13.20 long-term memory, complementing
:mod:`memory_writeback` (which persists learned facts) and :mod:`memory_semantic_index`
(which recalls them by similarity). Given the user's stored memories, it rewrites an
incoming query *before* it reaches ``entity_resolver`` / ``query_planner`` so the pipeline
sees the user's canonical vocabulary and habitual filters.

Two orthogonal transforms are applied:

* **Canonical aliases** — a mention the user always spells one way is replaced with its
  canonical entity id (memory kind ``'entity_alias'``), so entity resolution starts from
  the resolved id instead of re-guessing.
* **Preferred filters** — filters the user habitually applies (memory kind
  ``'preferred_filter'``) are injected as *defaults*, never overriding a filter the query
  already carries.

Everything is store-free, network-free and deterministic:

* :func:`apply_aliases` — substitute mentions via a canonical alias map.
* :func:`inject_default_filters` — add only absent filter keys.
* :func:`personalize` — fold a list of memory records into a frozen
  :class:`PersonalizedQuery`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PersonalizedQuery:
    """Query after §13.20 personalization: rewritten ``mentions`` and merged ``filters``.

    Frozen and JSON-serialisable via :meth:`as_dict`. ``applied`` records which kinds of
    personalization actually fired (применённые преобразования / applied transforms) — it
    contains ``'alias'`` if any mention was substituted and ``'filter'`` if any default
    filter was injected, so callers can audit what memory changed.
    """

    mentions: tuple[str, ...]
    filters: dict[str, Any]
    applied: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{mentions, filters, applied}`` with ``filters`` shallow-copied.

        The returned ``filters`` is a *distinct* object from this instance's ``filters``
        (отдельная копия / independent copy), so mutating it cannot corrupt the frozen
        query. ``mentions`` and ``applied`` are returned as lists for JSON friendliness.
        """
        return {
            "mentions": list(self.mentions),
            "filters": dict(self.filters),
            "applied": list(self.applied),
        }


def apply_aliases(mentions: list[str], alias_map: dict[str, str]) -> list[str]:
    """Replace each mention by its canonical id when present in ``alias_map`` (§13.20).

    A mention found as a key in ``alias_map`` is swapped for its canonical value (канонический
    id / canonical id); a mention absent from the map is kept verbatim (без изменений /
    unchanged). Order and length are preserved. E.g. with ``{'p53': 'HGNC:11998'}``,
    ``['p53', 'BRCA1'] → ['HGNC:11998', 'BRCA1']``.
    """
    return [alias_map.get(mention, mention) for mention in mentions]


def inject_default_filters(filters: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Add default filter keys that are *absent* from ``filters`` (§13.20 preferred filters).

    Returns a new dict: every key of ``filters`` is preserved as-is, and each key of
    ``defaults`` is added *only* if it is not already present (никогда не переопределяет /
    never overrides an existing key). The input ``filters`` is not mutated.
    """
    merged = dict(filters)
    for key, value in defaults.items():
        if key not in merged:
            merged[key] = value
    return merged


def personalize(
    mentions: list[str],
    filters: dict[str, Any],
    memory: list[dict[str, Any]],
) -> PersonalizedQuery:
    """Fold §13.20 memory records into a personalized query (aliases + preferred filters).

    ``memory`` is a list of records; only two kinds are consulted:

    * ``{'kind': 'entity_alias', 'mention': <str>, 'canonical': <str>}`` — builds the alias
      map used by :func:`apply_aliases`.
    * ``{'kind': 'preferred_filter', 'key': <str>, 'value': <any>}`` — builds the defaults
      injected by :func:`inject_default_filters`.

    Other kinds are ignored. The result's ``applied`` gains ``'alias'`` iff some mention was
    actually substituted, and ``'filter'`` iff some default filter was actually injected
    (a default whose key already existed does not count). An empty ``memory`` leaves
    ``mentions`` and ``filters`` untouched with empty ``applied``.
    """
    alias_map: dict[str, str] = {}
    defaults: dict[str, Any] = {}
    for record in memory:
        kind = record.get("kind")
        if kind == "entity_alias":
            alias_map[record["mention"]] = record["canonical"]
        elif kind == "preferred_filter":
            defaults[record["key"]] = record["value"]

    new_mentions = apply_aliases(mentions, alias_map)
    new_filters = inject_default_filters(filters, defaults)

    applied: list[str] = []
    if new_mentions != mentions:
        applied.append("alias")
    if set(new_filters) != set(filters):
        applied.append("filter")

    return PersonalizedQuery(
        mentions=tuple(new_mentions),
        filters=new_filters,
        applied=tuple(applied),
    )
