"""Цепочка происхождения слияний/разделений — merge/split lineage (§16.6/§16.7).

When entities are merged (or a node is split and its pieces re-homed), the losing side
is not deleted — it is stamped with ``superseded_by`` pointing at its successor, so the
merge history is preserved (§16.6). This module reconstructs that lineage by walking the
``superseded_by`` pointers from any historical id up to its live *canonical* head,
complementing :mod:`kg_common.storage.node_versioning` (which writes the pointers) without
duplicating its transition logic.

Поведение / behaviour:

* ``superseded_by`` may be a scalar id (``str``) or a list — the first element wins, so a
  split that fanned out records its primary successor as ``[primary, *others]``.
* A node without ``superseded_by`` (absent, ``None`` or empty) is its own canonical head.
* Cycles (``a -> b -> a``) are detected and rejected with :class:`ValueError`; a pointer to
  a missing id surfaces as :class:`KeyError`.

Kuzu note: these custom props are not queryable columns — callers read them via
``get_node`` and pass a plain ``Mapping[id, node]`` here (tests build a temp store dict).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProvenanceChain:
    """Разрешённая линия происхождения — the ordered path to a canonical head (§16.7).

    :param entity_id: the id the walk started from.
    :param canonical_id: the live head reached (a node without ``superseded_by``).
    :param ancestors: ordered ids from ``entity_id`` up to — but excluding — the head.
    :param depth: number of hops walked; equal to ``len(ancestors)``.
    """

    entity_id: str
    canonical_id: str
    ancestors: tuple[str, ...]
    depth: int

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view — сериализуемое представление цепочки."""
        return {
            "entity_id": self.entity_id,
            "canonical_id": self.canonical_id,
            "ancestors": list(self.ancestors),
            "depth": self.depth,
        }


def _successor(node: Mapping[str, Any]) -> str | None:
    """Return the next id via ``superseded_by`` — first element if a list (§16.6)."""
    nxt = node.get("superseded_by")
    if isinstance(nxt, (list, tuple)):
        nxt = nxt[0] if nxt else None
    if nxt is None or nxt == "":
        return None
    return str(nxt)


def build_chain(entity_id: str, nodes: Mapping[str, Mapping[str, Any]]) -> ProvenanceChain:
    """Walk ``superseded_by`` from ``entity_id`` to its canonical head — линия (§16.7).

    Follows the pointer chain, collecting every id up to (but not including) the head into
    ``ancestors``. Raises :class:`ValueError` on a cycle and :class:`KeyError` when a
    referenced id is absent from ``nodes``.
    """
    ancestors: list[str] = []
    seen: set[str] = set()
    current = entity_id
    while True:
        if current in seen:
            raise ValueError(f"cycle detected in superseded_by chain at {current!r}")
        seen.add(current)
        node = nodes[current]  # KeyError on a missing (intermediate) id — by design.
        nxt = _successor(node)
        if nxt is None:
            return ProvenanceChain(
                entity_id=entity_id,
                canonical_id=current,
                ancestors=tuple(ancestors),
                depth=len(ancestors),
            )
        ancestors.append(current)
        current = nxt


def resolve_canonical(entity_id: str, nodes: Mapping[str, Mapping[str, Any]]) -> str:
    """Follow ``superseded_by`` to the canonical head id — каноническая голова (§16.7).

    Thin wrapper over :func:`build_chain`; shares its cycle (:class:`ValueError`) and
    missing-id (:class:`KeyError`) semantics.
    """
    return build_chain(entity_id, nodes).canonical_id
