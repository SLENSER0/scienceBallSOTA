"""Пропагация решений ревью в индексы — index payload patch builder (§16.6).

After a curator resolves a review item (accept / reject / correct / merge /
mark_verified), the corresponding search-index documents in Qdrant and OpenSearch
must have their payload / ``_source`` updated so filters like ``verified=true`` or
``review_status='accepted'`` stay consistent with the graph. This module is the pure
builder for that step: it maps a review *action* + the resolved *target* to the exact
field deltas (:class:`IndexPatch`) that a downstream writer pushes into both indices.

Модуль не выполняет сетевых вызовов — no client calls, no I/O. It only computes the
patch; the caller applies it to Qdrant (``set_payload``) and OpenSearch (partial
update) for every affected ``doc_id``.

Действия / actions and their field deltas:

* ``accept``       -> ``{review_status: 'accepted', verified: True}``
* ``reject``       -> ``{review_status: 'rejected', verified: False}``
* ``correct``      -> ``{review_status: 'corrected', verified: True}`` plus
  ``confidence`` when the target carries one.
* ``mark_verified``-> ``{verified: True}``
* ``merge``        -> ``{canonical_id: <target.canonical_id>}``

Any other action (e.g. ``alias_add``) does not propagate to the indices —
:func:`applies_to` returns ``False`` and :func:`build_patch` raises ``ValueError``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# Действия, влияющие на индексы / actions that propagate to the search indices.
_PROPAGATING: frozenset[str] = frozenset({"accept", "reject", "correct", "mark_verified", "merge"})


@dataclass(frozen=True)
class IndexPatch:
    """Патч полезной нагрузки индекса — payload delta for search docs (§16.6).

    :param doc_ids: index document ids the patch must be applied to.
    :param fields: field name -> new value delta to SET on each document.
    """

    doc_ids: tuple[str, ...] = ()
    fields: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # Нормализуем поля к неизменяемому dict / normalise fields to a plain dict.
        object.__setattr__(self, "fields", dict(self.fields or {}))

    def as_dict(self) -> dict[str, Any]:
        """Return a serialisable view — сериализуемое представление патча (§16.6)."""
        return {"doc_ids": list(self.doc_ids), "fields": dict(self.fields)}


def applies_to(action: str) -> bool:
    """True only for the five index-propagating actions — распространяется ли (§16.6)."""
    return action in _PROPAGATING


def build_patch(
    action: str,
    target: Mapping[str, Any],
    *,
    doc_ids: Sequence[str],
) -> IndexPatch:
    """Compute the :class:`IndexPatch` for ``action`` on ``target`` (§16.6).

    :param action: review action; must be one of the propagating actions.
    :param target: resolved review target (canonical node / decision payload).
    :param doc_ids: index document ids to patch.
    :raises ValueError: if ``action`` is not an index-propagating action.
    """
    if not applies_to(action):
        raise ValueError(f"action не пропагируется в индексы / non-propagating action: {action!r}")

    fields: dict[str, Any] = {}
    if action == "accept":
        fields = {"review_status": "accepted", "verified": True}
    elif action == "reject":
        fields = {"review_status": "rejected", "verified": False}
    elif action == "correct":
        fields = {"review_status": "corrected", "verified": True}
        if "confidence" in target:
            fields["confidence"] = target["confidence"]
    elif action == "mark_verified":
        fields = {"verified": True}
    elif action == "merge":
        fields = {"canonical_id": target["canonical_id"]}

    return IndexPatch(doc_ids=tuple(doc_ids), fields=fields)
