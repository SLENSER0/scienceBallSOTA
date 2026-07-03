"""Edge-signature validation for upsert-time rejection (§3.16).

Схема рёбер (*edge schema*, :data:`kg_schema.relationships.EDGE_SCHEMA`) уже объявляет,
какие тройки ``(from_label, rel_type, to_label)`` допустимы, а
:func:`kg_schema.relationships.is_valid_edge` умеет их проверять — но эта проверка нигде
не *принуждается* при записи ребра (audit §3.16). Этот модуль — тонкая обёртка-страж
(*guard*), которую слой upsert вызывает перед созданием связи.

``validate_edge_signature`` поднимает :class:`EdgeSignatureError` (подкласс
``ValueError``), когда тройка не найдена в :data:`EDGE_SCHEMA`; в сообщении названа
нарушающая сигнатура (*offending signature*) и подсказка с разрешёнными целями
(*allowed targets*). ``is_allowed_signature`` — булев вариант без исключения, а
``allowed_targets`` возвращает отсортированный конкретный набор допустимых ``to``-меток
для пары ``(from_label, rel_type)`` (виртуальная метка ``Entity`` разворачивается в
:data:`kg_schema.labels.ENTITY_LABELS`, как и в ``is_valid_edge``).

Инвариант (*invariant*): ``to in allowed_targets(f, r)`` тогда и только тогда, когда
``is_allowed_signature(f, r, to)`` — обе опираются на одну и ту же логику разворачивания
``Entity``, так что подсказка в ошибке всегда совпадает с тем, что реально пройдёт.

Kuzu note: кастомные свойства узла НЕ являются запрашиваемыми колонками — их читают через
``get_node()``; страж работает только с метками рёбер, которые входят в базовые колонки.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_schema.labels import ENTITY_LABELS
from kg_schema.relationships import EDGE_SCHEMA, ENTITY, is_valid_edge


@dataclass(frozen=True)
class EdgeSignature:
    """An immutable ``(from_label, rel_type, to_label)`` edge triple (§3.16).

    Attributes
    ----------
    from_label:
        Label of the source node (e.g. ``"Person"``).
    rel_type:
        Relationship type carried by the edge (e.g. ``"MEMBER_OF"``).
    to_label:
        Label of the target node (e.g. ``"Lab"``).
    """

    from_label: str
    rel_type: str
    to_label: str

    def as_dict(self) -> dict[str, str]:
        """Serialise to a flat, JSON-friendly dict (§3.16)."""
        return {
            "from_label": self.from_label,
            "rel_type": self.rel_type,
            "to_label": self.to_label,
        }

    def __str__(self) -> str:
        """Cypher-ish rendering ``From-[:REL]->To`` for error messages."""
        return f"{self.from_label}-[:{self.rel_type}]->{self.to_label}"


class EdgeSignatureError(ValueError):
    """Raised when an edge triple is not declared in :data:`EDGE_SCHEMA` (§3.16).

    Carries the offending :attr:`signature` and the :attr:`allowed` targets so the
    caller can surface a precise, actionable rejection at upsert time.
    """

    def __init__(self, from_label: str, rel_type: str, to_label: str, allowed: list[str]) -> None:
        self.signature = EdgeSignature(from_label, rel_type, to_label)
        self.allowed: tuple[str, ...] = tuple(allowed)
        if self.allowed:
            hint = f"allowed targets for {from_label}-[:{rel_type}]->: {list(self.allowed)}"
        else:
            hint = f"no declared targets for {from_label!r} via [:{rel_type}]"
        super().__init__(f"invalid edge signature {self.signature}; {hint}")


def _expand(label: str) -> set[str]:
    """Expand the virtual ``Entity`` label to concrete :data:`ENTITY_LABELS`."""
    return set(ENTITY_LABELS) if label == ENTITY else {label}


def allowed_targets(from_label: str, rel_type: str) -> list[str]:
    """Return the sorted concrete ``to``-labels allowed for ``(from_label, rel_type)``.

    Scans :data:`EDGE_SCHEMA` for declared signatures matching ``from_label`` (with
    ``Entity`` expansion) and ``rel_type``, collecting each concrete target. The virtual
    ``Entity`` target expands to :data:`ENTITY_LABELS`, so membership matches
    :func:`is_allowed_signature` exactly. Unknown ``from_label`` / ``rel_type`` yield
    ``[]`` (nothing is allowed).
    """
    targets: set[str] = set()
    for f, r, t in EDGE_SCHEMA:
        if r != rel_type:
            continue
        if from_label in _expand(f):
            targets |= _expand(t)
    return sorted(targets)


def is_allowed_signature(from_label: str, rel_type: str, to_label: str) -> bool:
    """Return ``True`` iff ``(from_label, rel_type, to_label)`` is a declared edge (§3.16).

    Thin, side-effect-free delegate to :func:`kg_schema.relationships.is_valid_edge`
    (``Entity`` expands to :data:`ENTITY_LABELS`).
    """
    return is_valid_edge(from_label, rel_type, to_label)


def validate_edge_signature(from_label: str, rel_type: str, to_label: str) -> None:
    """Raise :class:`EdgeSignatureError` unless the edge triple is declared (§3.16).

    This is the enforcement point missing from the audit: call it before creating any
    relationship so undeclared ``(from, rel, to)`` combinations are rejected at
    upsert time. Returns ``None`` for a valid signature.
    """
    if is_valid_edge(from_label, rel_type, to_label):
        return
    raise EdgeSignatureError(from_label, rel_type, to_label, allowed_targets(from_label, rel_type))


__all__ = [
    "EdgeSignature",
    "EdgeSignatureError",
    "allowed_targets",
    "is_allowed_signature",
    "validate_edge_signature",
]
