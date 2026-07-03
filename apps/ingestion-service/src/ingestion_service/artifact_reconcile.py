"""Idempotent re-ingest reconciliation and orphan cleanup (§5.5).

When a document is re-ingested (a new source version replaces an older parse), the
object store may still hold artifacts produced by the *previous* parse. This module
computes a deterministic :class:`ReconcilePlan` from the set of artifact keys already
present in the store and the set of keys named by the new parse manifest:

* ``keep``   — keys present in both (unchanged, no work needed);
* ``delete`` — stale keys present in the store but absent from the new manifest
  (orphans left behind by an earlier version) — safe to remove;
* ``create`` — keys named by the new manifest not yet present in the store.

:func:`is_doc_prefixed` guards that a key belongs to ``documents/doc:<id>/`` so a
reconcile for one document never proposes deleting another document's objects.

Идемпотентная переингестия и очистка «сирот» (§5.5): по множествам ключей в
хранилище и в новом манифесте строится план keep/delete/create; префиксная
проверка не даёт удалять артефакты чужого документа.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ReconcilePlan:
    """Immutable plan for reconciling stored artifacts against a new manifest (§5.5).

    Неизменяемый план сверки артефактов с новым манифестом.
    """

    keep: tuple[str, ...]
    delete: tuple[str, ...]
    create: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise the plan to a plain JSON-safe dict of sorted key lists.

        Сериализация плана в обычный dict со списками ключей.
        """
        return {
            "keep": list(self.keep),
            "delete": list(self.delete),
            "create": list(self.create),
        }


def reconcile_artifacts(existing_keys: list[str], manifest_keys: list[str]) -> ReconcilePlan:
    """Compute the keep/delete/create plan for an idempotent re-ingest (§5.5).

    ``keep`` are keys present in both inputs; ``delete`` are existing keys absent from
    the new manifest (orphans from a prior version); ``create`` are manifest keys not
    yet present. All three tuples are sorted and mutually disjoint.

    Построение плана keep/delete/create для идемпотентной переингестии: keep — общие
    ключи, delete — «сироты» прежней версии, create — новые ключи манифеста.
    """
    existing = set(existing_keys)
    manifest = set(manifest_keys)
    return ReconcilePlan(
        keep=tuple(sorted(existing & manifest)),
        delete=tuple(sorted(existing - manifest)),
        create=tuple(sorted(manifest - existing)),
    )


def is_doc_prefixed(key: str, doc_id: str) -> bool:
    """Return ``True`` iff ``key`` lives under ``documents/doc:<doc_id>/`` (§5.5).

    Used to fence reconcile so it only ever touches one document's objects.

    Проверка, что ключ относится к каталогу ``documents/doc:<doc_id>/``.
    """
    return key.startswith(f"documents/doc:{doc_id}/")
