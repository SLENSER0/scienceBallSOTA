"""§3.7 — completeness of *edge-level provenance* properties (pure Python).

Полнота происхождения ребра (*edge-level provenance completeness*): проверяет, что плоский
словарь ребра несёт обязательные свойства происхождения из §3.7 — ``confidence``,
``extractor_run_id``, ``created_at``, ``schema_version`` — а для фактических связей
(:data:`kg_schema.relationships.FACTUAL_RELS`) ещё и непустой ``evidence_ids``.

Отличие от :mod:`kg_schema.relation_validation` (§3.19): там проверяется только *сигнатура*
``(source_label, rel_type, target_label)`` — допустима ли тройка по схеме. Здесь схема тройки
не трогается вовсе; проверяется *наличие и валидность значений* свойств происхождения на уже
собранном ребре. Модуль строится ПОВЕРХ ``relationships.py`` — переиспользует
:data:`FACTUAL_RELS` и ничего в нём не переопределяет.

* :data:`EDGE_PROVENANCE_PROPS` — базовый кортеж обязательных свойств (§3.7), общий для всех
  рёбер, в стабильном порядке отчёта.
* :func:`required_props_for` — базовые свойства плюс ``evidence_ids`` для фактических связей.
* :func:`validate_edge_provenance` → :class:`EdgeProvenanceCheck`: отсутствующее/пустое
  обязательное свойство → ``ok=False``; ``confidence`` вне ``[0, 1]`` → ``ok=False``; пустой
  ``evidence_ids`` на фактической связи → ``ok=False``.

Kuzu note: кастомные свойства узла/ребра НЕ являются запрашиваемыми колонками — их читают
через ``get_node()`` (в ``RETURN`` идут только базовые колонки). Проверка работает над уже
собранным ``dict`` ребра, а не над Cypher-``RETURN`` пользовательских свойств.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from kg_schema.relationships import FACTUAL_RELS

# Mandatory provenance props on *every* edge (§3.7), in stable report order.
EDGE_PROVENANCE_PROPS: tuple[str, ...] = (
    "confidence",
    "extractor_run_id",
    "created_at",
    "schema_version",
)

# Extra provenance prop required only on factual relations (§3.7).
_EVIDENCE_IDS: str = "evidence_ids"


@dataclass(frozen=True)
class EdgeProvenanceCheck:
    """Immutable result of checking one edge's provenance completeness (§3.7).

    Attributes
    ----------
    ok:
        ``True`` iff every required provenance prop is present and non-blank,
        ``confidence`` lies in ``[0, 1]``, and (for factual rels) ``evidence_ids``
        is a non-empty collection.
    missing:
        Required props that are absent, blank, or invalid, in report order.
    reason:
        Human-readable explanation of the rejection, or ``""`` when :attr:`ok`.
    """

    ok: bool
    missing: tuple[str, ...] = ()
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a flat, JSON-friendly dict (§3.7)."""
        return {"ok": self.ok, "missing": list(self.missing), "reason": self.reason}


def required_props_for(rel_type: str) -> tuple[str, ...]:
    """Required provenance props for ``rel_type`` (§3.7).

    Base :data:`EDGE_PROVENANCE_PROPS` for any edge, plus ``evidence_ids`` when
    ``rel_type`` is a factual relation (:data:`FACTUAL_RELS`).
    """
    if rel_type in FACTUAL_RELS:
        return (*EDGE_PROVENANCE_PROPS, _EVIDENCE_IDS)
    return EDGE_PROVENANCE_PROPS


def _is_blank(value: Any) -> bool:
    """True iff ``value`` is ``None`` or a blank/empty string."""
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def validate_edge_provenance(edge: Mapping[str, Any], rel_type: str) -> EdgeProvenanceCheck:
    """Check that ``edge`` carries valid §3.7 provenance for ``rel_type``.

    Rules (§3.7):

    * every prop in :func:`required_props_for` must be present and non-blank;
    * ``confidence`` must be a real number in ``[0, 1]``;
    * ``evidence_ids`` on a factual relation must be a non-empty collection.
    """
    required = required_props_for(rel_type)
    missing: list[str] = []

    for prop in required:
        if prop not in edge or _is_blank(edge[prop]):
            missing.append(prop)

    # confidence range — only meaningful when present and non-blank.
    if "confidence" not in missing:
        conf = edge["confidence"]
        if (
            isinstance(conf, bool)
            or not isinstance(conf, (int, float))
            or not (0.0 <= float(conf) <= 1.0)
        ):
            missing.append("confidence")

    # evidence_ids must be a non-empty collection on factual rels.
    if rel_type in FACTUAL_RELS and _EVIDENCE_IDS not in missing:
        evidence = edge[_EVIDENCE_IDS]
        if isinstance(evidence, (str, bytes)) or not _has_items(evidence):
            missing.append(_EVIDENCE_IDS)

    # De-duplicate while preserving report order (confidence may appear twice).
    ordered = tuple(p for p in required if p in set(missing))

    if not ordered:
        return EdgeProvenanceCheck(ok=True)
    reason = f"missing/invalid provenance props for {rel_type!r}: {', '.join(ordered)}"
    return EdgeProvenanceCheck(ok=False, missing=ordered, reason=reason)


def _has_items(value: Any) -> bool:
    """True iff ``value`` is a non-empty sized collection."""
    try:
        return len(value) > 0
    except TypeError:
        return False
