"""Roll-up shape-conformance report for FAIR export (§24.19).

Небольшая надстройка над :func:`kg_schema.shapes.validate_nodes`: она валидирует
набор узлов и агрегирует итог в неизменяемый :class:`ShapeReport` — сколько узлов
всего, сколько конформны, полный список нарушений (severity ``violation``) и
разбивка по меткам (``by_label``). Реализация чистая (pure Python), без побочных
эффектов, поэтому пригодна для ingest, CI и экспорта.

Thin roll-up over :func:`kg_schema.shapes.validate_nodes`: it validates a batch
of nodes and aggregates the outcome into a frozen :class:`ShapeReport` — the
total node count, how many conform, the flat list of hard violations (severity
``violation``) and a per-label breakdown (``by_label``). Pure Python, no side
effects, so it runs during ingest, CI and FAIR export alike.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from kg_schema.shapes import SEVERITY_VIOLATION, validate_nodes


def _node_label(node: Mapping[str, Any]) -> str | None:
    """Метка узла, допускающая список ``labels`` / node label, tolerating list."""
    label = node.get("label")
    if label is None:
        labels = node.get("labels") or []
        label = labels[0] if labels else None
    return None if label is None else str(label)


@dataclass(frozen=True)
class ShapeViolationEntry:
    """Одно жёсткое нарушение на узле / one hard violation on a node (§24.19)."""

    index: int
    label: str | None
    field: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "label": self.label,
            "field": self.field,
            "message": self.message,
        }


@dataclass(frozen=True)
class ShapeReport:
    """Агрегированный отчёт о конформности / aggregate conformance report (§24.19)."""

    total: int
    conformant: int
    violations: tuple[ShapeViolationEntry, ...]
    by_label: dict[str, dict[str, int]]

    @property
    def nonconformant(self) -> int:
        """Узлы с хотя бы одним нарушением / nodes with >=1 violation."""
        return self.total - self.conformant

    @property
    def ratio(self) -> float:
        """Доля конформных узлов, 0.0 при пустом входе / conformance ratio."""
        return self.conformant / self.total if self.total else 0.0

    @property
    def conforms(self) -> bool:
        """Все ли узлы конформны / whether every node conforms."""
        return self.conformant == self.total

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "conformant": self.conformant,
            "nonconformant": self.nonconformant,
            "ratio": self.ratio,
            "conforms": self.conforms,
            "violations": [v.as_dict() for v in self.violations],
            "by_label": {k: dict(v) for k, v in self.by_label.items()},
        }


def build_shape_report(nodes: Iterable[Mapping[str, Any]]) -> ShapeReport:
    """Провалидировать узлы и собрать :class:`ShapeReport` (§24.19).

    Validate ``nodes`` via :func:`kg_schema.shapes.validate_nodes` and roll the
    per-node results up into a frozen report. Only ``severity == "violation"``
    issues become :class:`ShapeViolationEntry` items — warnings/info are ignored.
    ``by_label`` maps each seen label to ``{total, conformant}`` counts.
    """
    node_list = list(nodes)
    report = validate_nodes(node_list)
    results = report["results"]

    violations: list[ShapeViolationEntry] = []
    by_label: dict[str, dict[str, int]] = {}
    conformant = 0
    for index, (node, result) in enumerate(zip(node_list, results, strict=True)):
        label = _node_label(node)
        key = str(label)
        bucket = by_label.setdefault(key, {"total": 0, "conformant": 0})
        bucket["total"] += 1
        if result["conforms"]:
            conformant += 1
            bucket["conformant"] += 1
        for violation in result["violations"]:
            if violation["severity"] != SEVERITY_VIOLATION:
                continue
            violations.append(
                ShapeViolationEntry(
                    index=index,
                    label=label,
                    field=violation["field"],
                    message=violation["message"],
                )
            )

    return ShapeReport(
        total=len(node_list),
        conformant=conformant,
        violations=tuple(violations),
        by_label=by_label,
    )


__all__ = [
    "ShapeReport",
    "ShapeViolationEntry",
    "build_shape_report",
]
