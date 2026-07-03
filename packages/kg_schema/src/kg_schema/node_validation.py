"""§3.18 — required-property validation for a single node dict (pure Python).

Валидация обязательных свойств узла (*required-property validation*): проверяет, что
плоский словарь узла несёт те доменные свойства, которые обязаны присутствовать для его
метки (§3.18). Это дополняет SHACL-подобные формы из :mod:`kg_schema.shapes`: там
проверяется провенанс/контролируемые словари для FAIR-экспорта, а здесь — минимальный
семантический payload узла (например, у ``Measurement`` обязаны быть ``value_normalized``
и ``property_name``, у ``Evidence`` — ``doc_id``).

Каталог :data:`REQUIRED_PROPS` (метка → кортеж имён обязательных свойств) авторский и
задан явно, ключи берутся из :class:`kg_schema.labels.NodeLabel`, чтобы имена меток не
расходились с онтологией (§8.1). Модуль НИЧЕГО не переопределяет и ничего не пишет в граф —
это чистая функция над ``dict``.

* :func:`validate_node` → :class:`NodeValidation` (``ok`` / ``label`` / ``missing`` /
  ``errors``): для метки без объявленных ограничений результат всегда ``ok=True``; узел без
  метки — структурная ошибка (``errors``), а не ``missing``.
* :func:`missing_fields` — только список отсутствующих обязательных свойств для метки узла.

Kuzu note: кастомные свойства узла НЕ являются запрашиваемыми колонками — их читают через
``get_node()`` (в ``RETURN`` идут только базовые колонки). Поэтому эта проверка работает над
уже прочитанным ``dict`` узла, а не над результатом Cypher-``RETURN``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from kg_schema.labels import NodeLabel

# Required domain properties per label (§3.18): label → tuple of prop names that MUST be
# present (non-empty) on a node of that label. Keys use NodeLabel values so they never drift
# from the ontology (§8.1). Labels absent here carry no required-property constraint.
REQUIRED_PROPS: dict[str, tuple[str, ...]] = {
    NodeLabel.MEASUREMENT.value: ("value_normalized", "property_name"),
    NodeLabel.EVIDENCE.value: ("doc_id",),
    NodeLabel.CLAIM.value: ("text",),
    NodeLabel.FINDING.value: ("text",),
    NodeLabel.UNIT.value: ("symbol",),
}


@dataclass(frozen=True)
class NodeValidation:
    """Immutable result of validating one node's required properties (§3.18).

    Attributes
    ----------
    ok:
        ``True`` iff the node has a label and no required property is missing.
    label:
        The node's resolved label, or ``None`` when the node carries none.
    missing:
        Names of required properties that are absent / empty for :attr:`label`.
    errors:
        Structural problems (e.g. a node with no label); distinct from
        :attr:`missing`, which lists per-label required-property gaps.
    """

    ok: bool
    label: str | None
    missing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a flat, JSON-friendly dict (§3.18).

        Lists are copied so callers cannot mutate the frozen result through them.
        """
        return {
            "ok": self.ok,
            "label": self.label,
            "missing": list(self.missing),
            "errors": list(self.errors),
        }


def _node_label(node: Mapping[str, Any]) -> str | None:
    """Return the node's single label, tolerating a ``labels`` list (§3.18)."""
    label = node.get("label")
    if label is None:
        labels = node.get("labels") or []
        label = labels[0] if labels else None
    return None if label is None else str(label)


def _is_missing(node: Mapping[str, Any], name: str) -> bool:
    """A property is missing if absent, ``None``, or a blank string (§3.18)."""
    if name not in node:
        return True
    value = node[name]
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def required_props(label: str | None) -> tuple[str, ...]:
    """Return the required-property names declared for ``label`` (§3.18).

    An unknown / unmodelled / ``None`` label has no constraints → ``()``.
    """
    if label is None:
        return ()
    return REQUIRED_PROPS.get(label, ())


def missing_fields(node: Mapping[str, Any]) -> list[str]:
    """Return the required properties absent from ``node`` for its label (§3.18).

    A node with no label, or a label without declared constraints, yields ``[]``
    (there is nothing that must be present). Order follows :data:`REQUIRED_PROPS`.
    """
    label = _node_label(node)
    return [name for name in required_props(label) if _is_missing(node, name)]


def validate_node(node: Mapping[str, Any]) -> NodeValidation:
    """Validate one node dict against its label's required properties (§3.18).

    A node without a label is a structural error (``ok=False``, reported in
    :attr:`NodeValidation.errors`). A known label with all required properties present
    → ``ok=True``. An unknown / unmodelled label carries no constraints, so it also
    validates as ``ok=True`` with empty ``missing``.
    """
    label = _node_label(node)
    if label is None:
        return NodeValidation(ok=False, label=None, errors=["node has no 'label'"])
    missing = missing_fields(node)
    return NodeValidation(ok=not missing, label=label, missing=missing)


def known_labels() -> frozenset[str]:
    """Labels that declare at least one required property (§3.18)."""
    return frozenset(REQUIRED_PROPS)


__all__ = [
    "REQUIRED_PROPS",
    "NodeValidation",
    "known_labels",
    "missing_fields",
    "required_props",
    "validate_node",
]
