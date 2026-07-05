"""Destructive corpus-source purge — remove a source «из системы в целом» (§2/§4).

RU: Полное, НЕОБРАТИМОЕ удаление источника корпуса и ВСЕГО производного от него —
узлов графа, записи в реестре источников и точек векторного индекса. Источник
идентифицируется id своего узла (то, что ``/documents/corpus`` отдаёт как ``doc_id``,
§1). Каждый производный узел (Chunk / Evidence / Measurement + doc-scoped узлы) несёт
этот id в запрашиваемой колонке ``doc_id`` (конвейер ингеста ставит
``doc_id=<id узла-документа>``).

EN: Removes a corpus source and EVERYTHING derived from it, irreversibly. A source is
identified by its node id (what ``/documents/corpus`` returns as ``doc_id``, §1); every
derived node carries that id in its queryable ``doc_id`` column.

The graph cascade is ONE query that removes the source node AND all its derived
nodes+edges (§2)::

    MATCH (n:Node) WHERE n.id = $id OR n.doc_id = $id DETACH DELETE n

This is SAFE by construction: shared canonical / taxonomy entities (e.g. Material
«nickel») have no ``doc_id`` and a different ``id``, so they are NOT touched. It must
NEVER be widened to delete by name/label.

:func:`purge_source` (§4) additionally purges the source from the OTHER stores so it is
gone system-wide: the SQL source registry (``SourceRegistry.delete``, §3) and the
vector index (``qdrant_server_store.delete_by_doc``, §3). Both side stores are optional
and guarded — a missing or failing one must NEVER abort the graph delete. The whole
operation is idempotent: purging a non-existent source deletes 0 nodes and is not an
error.
"""

from __future__ import annotations

from typing import Any, Protocol

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("source_delete")

# ONE cascade over the source node (matched by ``id``) and every derived node (matched
# by its ``doc_id`` column). Shared canonical/taxonomy nodes carry neither, so they
# survive. NEVER widen this predicate to name/label. / общий каскад по id ИЛИ doc_id.
_CASCADE_WHERE = "n.id = $id OR n.doc_id = $id"
_COUNT_CASCADE = f"MATCH (n:Node) WHERE {_CASCADE_WHERE} RETURN count(n)"
_DELETE_CASCADE = f"MATCH (n:Node) WHERE {_CASCADE_WHERE} DETACH DELETE n"


class _RegistryLike(Protocol):
    """Minimal contract expected of the SQL source registry (``SourceRegistry.delete``)."""

    def delete(self, source_id: str) -> Any: ...


class _VectorLike(Protocol):
    """Minimal contract expected of the vector store (``delete_by_doc``)."""

    def delete_by_doc(self, doc_id: str) -> Any: ...


def delete_source_nodes(store: KuzuGraphStore, source_id: str) -> int:
    """Cascade-delete the source node and all its derived nodes+edges (§2).

    RU: Считает совпавшие узлы ДО удаления (``count()`` перед удалением, §2), затем
    выполняет единственный ``DETACH DELETE`` по ``n.id = $id OR n.doc_id = $id``.
    Возвращает число удалённых узлов. Общие канонические сущности не затрагиваются.
    Идемпотентно: для несуществующего источника вернёт 0 (удаление не запускается).

    EN: Queries ``count()`` first (before the delete, §2), then runs the single
    ``DETACH DELETE`` cascade removing the source node (by ``id``) together with every
    derived node (by ``doc_id``) and their edges. Returns the number of nodes removed
    (0 if the source does not exist — no write is issued).
    """
    params = {"id": source_id}
    rows = store.rows(_COUNT_CASCADE, params)
    deleted = int(rows[0][0]) if rows else 0
    if deleted:
        store.execute(_DELETE_CASCADE, params)
    return deleted


def purge_source(
    store: KuzuGraphStore,
    source_id: str,
    *,
    registry: _RegistryLike | None = None,
    vector: _VectorLike | None = None,
) -> dict[str, Any]:
    """Purge a corpus source from the graph AND the other stores (§4).

    RU: Оркестратор полного удаления. Граф удаляется ВСЕГДА (:func:`delete_source_nodes`);
    затем, если переданы, удаляются запись реестра (``registry.delete``, §3) и точки
    векторного индекса (``vector.delete_by_doc``, §3). Каждый побочный стор защищён
    try/except — его отсутствие или сбой не должны прерывать удаление графа
    (best-effort на встроенном профиле). Идемпотентно.

    EN: Deletes the graph first (always), then best-effort purges the SQL registry and
    the vector index when provided. Each side store is guarded so a missing/failing one
    never aborts the graph delete. Returns
    ``{source_id, deleted_nodes, registry_deleted, vector_purged}``. Idempotent:
    purging a non-existent source returns ``deleted_nodes=0`` (not an error).
    """
    deleted_nodes = delete_source_nodes(store, source_id)

    registry_deleted = False
    if registry is not None:
        try:
            registry.delete(source_id)
            registry_deleted = True
        except Exception:  # side store must never abort the graph delete (§4)
            _log.warning("source registry delete failed for %s", source_id, exc_info=True)

    vector_purged = False
    if vector is not None:
        try:
            vector.delete_by_doc(source_id)
            vector_purged = True
        except Exception:  # best-effort: swallow errors on the embedded profile (§3)
            _log.warning("vector delete_by_doc failed for %s", source_id, exc_info=True)

    return {
        "source_id": source_id,
        "deleted_nodes": deleted_nodes,
        "registry_deleted": registry_deleted,
        "vector_purged": vector_purged,
    }
