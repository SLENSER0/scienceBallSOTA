"""DELETE a corpus source «из системы в целом» — destructive purge endpoint (§5).

RU: Кнопка × на карточке источника корпуса удаляет источник и ВСЁ производное от него
— узлы графа (каскад по ``id``/``doc_id``), запись реестра источников и точки векторного
индекса. НЕОБРАТИМО. Источник идентифицируется id своего узла (то, что ``/documents/corpus``
отдаёт как ``doc_id``, §1). Доступ только у роли с правом «delete» (admin) — иначе 403.

EN: ``DELETE /api/v1/corpus/sources/{doc_id}`` removes a corpus source and EVERYTHING
derived from it, irreversibly. The graph cascade + side-store purge live in the
orchestrator :func:`kg_retrievers.source_delete.purge_source` (Core phase); this router
only role-gates the call and wires the stores the gateway exposes.

The endpoint is ROLE-GATED with :mod:`kg_common.rbac_policy`: only a role that holds the
``delete`` capability (``admin``) may call it — every other role gets 403. (The role is
spoofable via ``X-Role`` today — a separate known defect; the gate is still enforced.)
Idempotent: deleting a non-existent source returns ``deleted_nodes=0``, not an error.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api_gateway import audit
from api_gateway.auth import current_role, current_user
from api_gateway.deps import get_store
from kg_common import get_logger
from kg_common.rbac_policy import can
from kg_retrievers.source_delete import purge_source

_log = get_logger("corpus_source_delete")
router = APIRouter(prefix="/api/v1/corpus", tags=["corpus"])


def _source_registry() -> Any | None:
    """The gateway's :class:`SourceRegistry`, if it exposes one — else ``None`` (§5).

    The graph cascade is the always-on core of a source delete; the SQL registry purge
    is an optional side effect only wired when the gateway exposes a registry accessor
    (``api_gateway.deps.get_source_registry``). Guarded so a missing or failing accessor
    can NEVER block the destructive graph delete (``purge_source`` deletes the graph
    first and treats a ``None`` registry as "skip"). / реестр, если гейтвей его отдаёт.
    """
    try:
        from api_gateway import deps

        getter = getattr(deps, "get_source_registry", None)
        if getter is None:
            return None
        return getter()
    except Exception:  # pragma: no cover - defensive: never block the graph delete
        _log.warning("corpus_source_delete.registry_unavailable", exc_info=True)
        return None


@router.delete("/sources/{doc_id:path}")
def delete_corpus_source(
    doc_id: str,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict[str, Any]:
    """Purge a corpus source and everything derived from it (§5, DESTRUCTIVE, irreversible).

    RU: Роль-гейт по праву «delete» (только admin) — иначе 403. Затем оркестратор
    :func:`purge_source` удаляет граф (каскад по ``id``/``doc_id``) и, если гейтвей их
    отдаёт, чистит побочные хранилища. Возвращает
    ``{source_id, deleted_nodes, registry_deleted, vector_purged}``. Идемпотентно:
    несуществующий источник → ``deleted_nodes=0`` (не ошибка).

    EN: Enforces the ``delete`` capability (admin only) → 403 otherwise, then delegates
    to :func:`purge_source`, which removes the source node together with every derived
    node (matched by its ``doc_id`` column) and best-effort purges the side stores the
    gateway exposes. Shared canonical/taxonomy entities carry no ``doc_id`` and survive.
    Returns the orchestrator's purge dict verbatim.
    """
    if not can(role, "delete"):
        raise HTTPException(status_code=403, detail="role may not delete corpus sources")

    result = purge_source(get_store(), doc_id, registry=_source_registry())
    audit.record(
        "delete_corpus_source",
        user=user,
        role=role,
        detail={"doc_id": doc_id, "deleted_nodes": result["deleted_nodes"]},
    )
    return result
