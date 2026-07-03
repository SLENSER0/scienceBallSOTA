"""Keyword-store (Mode B) access-filter clause builder (§19.3).

RU: Построитель клаузы фильтра доступа для keyword-стора (Mode B, OpenSearch/BM25)
согласно §19.3. Дополняет :mod:`kg_retrievers.access_filter`, который выдаёт
только параметры Cypher и фильтр Qdrant, недостающей клаузой keyword-стора.
Переиспользует :class:`AccessScope`, :class:`SourceMeta` и
:func:`visible_source_ids` из :mod:`kg_retrievers.access_filter`, чтобы избежать
расхождения политик. Для администратора клауза пуста (``{}`` == без
ограничений); иначе формируется bool-фильтр OpenSearch по отсортированным,
дедуплицированным видимым ``source_id``. Пустая видимость даёт клаузу,
не совпадающую ни с чем (терм-лист пуст), но никогда ``{}``.

EN: Keyword-store (Mode B, OpenSearch/BM25) access-filter clause builder per
§19.3. Complements :mod:`kg_retrievers.access_filter` — which only emits Cypher
params and a Qdrant filter — with the missing keyword-store clause. It reuses
:class:`AccessScope`, :class:`SourceMeta` and :func:`visible_source_ids` from
:mod:`kg_retrievers.access_filter` to avoid policy drift. For an admin the clause
is empty (``{}`` meaning unrestricted); otherwise an OpenSearch ``bool`` filter is
built over the sorted, de-duplicated visible ``source_id`` values. Empty
visibility yields a clause matching nothing (empty terms list) but never ``{}``.

Pure python — no store access. Kuzu note: custom node props are NOT queryable
columns; callers RETURN base columns and read policy/owner via ``get_node()``
before constructing :class:`SourceMeta`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from kg_retrievers.access_filter import AccessScope, SourceMeta, visible_source_ids

# OpenSearch/BM25 field holding a document's owning source id (§19.3, Mode B).
KEYWORD_SOURCE_FIELD = "source_id"


def bm25_terms(scope: AccessScope, sources: Iterable[SourceMeta]) -> tuple[str, ...]:
    """Return the sorted, de-duplicated visible ``source_id`` tuple (§19.3).

    This is the exact id set embedded in the OpenSearch ``terms`` clause built by
    :func:`opensearch_access_filter`; BM25 keyword retrievers restrict candidate
    documents to these source ids. Admin scopes still receive the full visible
    set (which for an admin is every source id).
    """
    return tuple(sorted(visible_source_ids(scope, sources)))


def opensearch_access_filter(
    scope: AccessScope,
    sources: Iterable[SourceMeta],
) -> dict[str, Any]:
    """Build the OpenSearch/BM25 (Mode B) access-filter clause for ``scope`` (§19.3).

    For an admin the clause is ``{}`` (unrestricted). Otherwise it is a ``bool``
    filter restricting ``source_id`` to the sorted, de-duplicated visible ids::

        {'bool': {'filter': [{'terms': {'source_id': [...]}}]}}

    An empty visible set still yields the full clause with an empty terms list
    (matches nothing) — a non-admin scope never collapses to ``{}``.
    """
    if scope.is_admin:
        return {}
    return {
        "bool": {"filter": [{"terms": {KEYWORD_SOURCE_FIELD: list(bm25_terms(scope, sources))}}]}
    }


@dataclass(frozen=True)
class KeywordFilterResult:
    """Frozen result bundling the Mode-B keyword access filter (§19.3).

    ``is_admin`` mirrors the scope's admin flag; ``source_ids`` is the sorted,
    de-duplicated visible id tuple; ``clause`` is the OpenSearch clause (``{}``
    for admins).
    """

    is_admin: bool
    source_ids: tuple[str, ...]
    clause: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict projection for trace / round-trip (§19.3, house style)."""
        return {
            "is_admin": self.is_admin,
            "source_ids": list(self.source_ids),
            "clause": self.clause,
        }


def keyword_filter_result(
    scope: AccessScope,
    sources: Iterable[SourceMeta],
) -> KeywordFilterResult:
    """Assemble a :class:`KeywordFilterResult` for ``scope`` over ``sources`` (§19.3)."""
    return KeywordFilterResult(
        is_admin=scope.is_admin,
        source_ids=bm25_terms(scope, sources),
        clause=opensearch_access_filter(scope, sources),
    )
