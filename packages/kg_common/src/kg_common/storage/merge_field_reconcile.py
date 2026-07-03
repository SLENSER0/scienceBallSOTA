"""Action ``merge``: canonical field reconciliation — сведение полей при слиянии (§16.6).

:mod:`merge_guard` only *detects* verified-field conflicts and :func:`canonical_id`
only picks the *surviving* node id. Neither computes the merged property map that the
canonical node should actually carry. This module fills that gap: given the entities
being merged and the chosen canonical id, it reconciles every data field down to a
single winning value and records *which* source entity won each field.

Per-field precedence — приоритет выбора значения поля:

#. **non-null** — a ``None``/missing value is never chosen while any entity offers a
   non-null value (dominant gate; a verified ``None`` still loses to an unverified
   number);
#. **verified** — a field listed in an entity's ``verified_fields`` beats an unverified
   value, even one with higher confidence;
#. **higher confidence** — larger ``confidence`` wins among unverified values;
#. **newer ``valid_from``** — later ISO-8601 timestamp wins on equal confidence;
#. deterministic tie-break: lexicographically smallest source ``id``.

``aliases`` are unioned across all entities together with each entity's ``name`` (de-
duplicated, order-preserving). ``superseded_ids`` lists every non-canonical id. The
result is a frozen :class:`MergedNode` with :meth:`~MergedNode.as_dict`.

The module is pure and backend-agnostic — Kuzu custom node props are not queryable
columns, so callers read the reconciled fields via ``get_node()`` and never SELECT them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

# Structural / metadata keys — not treated as reconcilable data fields.
# Служебные ключи — не участвуют в сведении как поля-данные.
_RESERVED: frozenset[str] = frozenset(
    {"id", "name", "aliases", "verified_fields", "confidence", "valid_from"},
)


@dataclass(frozen=True)
class MergedNode:
    """Reconciled canonical node produced by a ``merge`` action (§16.6).

    :param canonical_id: id of the surviving node — идентификатор выжившего узла.
    :param fields: merged property map (field -> winning value).
    :param provenance: field -> id of the source entity whose value won.
    :param aliases: de-duplicated union of every entity's ``aliases`` and ``name``.
    :param superseded_ids: every non-canonical id folded into the canonical node.
    """

    canonical_id: str
    fields: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)
    superseded_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view — сериализуемое представление узла."""
        return asdict(self)


def _score(entity: Mapping[str, Any], name: str) -> tuple[int, int, float, str]:
    """Ranking key for ``entity``'s value of ``name`` — larger is better.

    Order mirrors the documented precedence: non-null gate, verified flag, confidence,
    then newer ``valid_from``. Higher tuples win; the caller breaks final ties by id.
    """
    value = entity.get(name)
    non_null = 0 if value is None else 1
    verified = 1 if name in (entity.get("verified_fields") or []) else 0
    try:
        confidence = float(entity.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    valid_from = str(entity.get("valid_from") or "")
    return (non_null, verified, confidence, valid_from)


def field_winner(entities: Sequence[Mapping[str, Any]], field_name: str) -> str | None:
    """Return the id of the entity whose value of ``field_name`` wins, or ``None``.

    ``None`` means no entity carries a non-null value for the field. Ties on the full
    precedence key are broken by the lexicographically smallest ``id`` for determinism.
    """
    best_id: str | None = None
    best_key: tuple[int, int, float, str] | None = None
    for entity in entities:
        key = _score(entity, field_name)
        if key[0] == 0:  # value is None/missing — never a standalone winner.
            continue
        eid = str(entity.get("id"))
        if best_key is None or key > best_key or (key == best_key and eid < str(best_id)):
            best_key = key
            best_id = eid
    return best_id


def _reconcilable_fields(entities: Sequence[Mapping[str, Any]]) -> list[str]:
    """Collect data-field names across ``entities`` (order-preserving, no reserved keys)."""
    names: list[str] = []
    seen: set[str] = set()
    for entity in entities:
        for name in entity:
            if name in _RESERVED or name in seen:
                continue
            seen.add(name)
            names.append(name)
    return names


def _merged_aliases(entities: Sequence[Mapping[str, Any]]) -> list[str]:
    """Union each entity's ``aliases`` list and ``name`` — de-duplicated, order-preserving."""
    aliases: list[str] = []
    seen: set[str] = set()
    for entity in entities:
        candidates = list(entity.get("aliases") or [])
        name = entity.get("name")
        if name is not None:
            candidates.append(name)
        for alias in candidates:
            if alias is None or alias in seen:
                continue
            seen.add(alias)
            aliases.append(str(alias))
    return aliases


def reconcile_fields(
    entities: Sequence[Mapping[str, Any]],
    canonical_id: str,
) -> MergedNode:
    """Reconcile ``entities`` into one :class:`MergedNode` under ``canonical_id`` (§16.6).

    Every data field present on any entity is resolved to a single winning value by the
    module's precedence (non-null > verified > confidence > newer ``valid_from`` > id).
    ``provenance`` records the source id that won each field; ``aliases`` unions names,
    and ``superseded_ids`` lists every non-canonical id.
    """
    if not entities:
        raise ValueError("reconcile_fields requires at least one entity")

    fields: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    by_id = {str(e.get("id")): e for e in entities}
    for name in _reconcilable_fields(entities):
        winner = field_winner(entities, name)
        if winner is None:  # no non-null value anywhere — skip the field entirely.
            continue
        fields[name] = by_id[winner].get(name)
        provenance[name] = winner

    superseded: list[str] = []
    seen_ids: set[str] = set()
    for entity in entities:
        eid = str(entity.get("id"))
        if eid == canonical_id or eid in seen_ids:
            continue
        seen_ids.add(eid)
        superseded.append(eid)

    return MergedNode(
        canonical_id=canonical_id,
        fields=fields,
        provenance=provenance,
        aliases=_merged_aliases(entities),
        superseded_ids=superseded,
    )
