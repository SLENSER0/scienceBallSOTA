"""§5.2.2 tabbed answer layout + numeric aggregates builder (§13.17).

Pure-python, deterministic projection layered on top of the already-prepared
synthesize/answer_assembler output. Берёт поля состояния агента (§13.11) —
``retrieved_experiments``, ``evidence``, ``visualization_payload``, ``gaps``,
``contradictions`` — и раскладывает их по шести вкладкам ответа (§5.2.2):
``summary``, ``experiments``, ``evidence``, ``graph``, ``gaps``, ``contradictions``.

Ничего здесь не трогает граф-стор и не зовёт LLM — модуль остаётся
unit-testable без засеянной Kuzu-базы. Kuzu note: custom node props are NOT
queryable columns — a retriever must RETURN base columns and read the rest via
``get_node``; by the time state reaches this module the rows already carry the
merged props as plain dicts, so nothing here touches the store.

Помимо раскладки по вкладкам модуль считает числовые агрегаты для вкладки
``summary``: диапазон эффекта по свойству (:func:`effect_range`) и счётчики
эксперименты/статьи/без-базлайна (:func:`aggregate_counts`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = ["AnswerTabs", "aggregate_counts", "build_tabs", "effect_range"]

# The six §5.2.2 tab keys, in display order.
_TAB_KEYS = ("summary", "experiments", "evidence", "graph", "gaps", "contradictions")

# Gap ``type`` marking an experiment without a control/baseline (§5.2.2 summary).
_MISSING_BASELINE = "missing_baseline"


@dataclass(frozen=True)
class AnswerTabs:
    """The six §5.2.2 answer tabs, each a JSON-ready ``dict`` payload.

    Field names are the tab keys themselves (snake_case == camelCase here), so
    :meth:`as_dict` renders exactly those six keys. Every tab defaults to an
    empty ``dict`` via :func:`build_tabs`, so the layout always carries all six.
    """

    summary: dict[str, Any]
    experiments: dict[str, Any]
    evidence: dict[str, Any]
    graph: dict[str, Any]
    gaps: dict[str, Any]
    contradictions: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to the six §5.2.2 tab keys (shallow-copies each tab dict)."""
        return {
            "summary": dict(self.summary),
            "experiments": dict(self.experiments),
            "evidence": dict(self.evidence),
            "graph": dict(self.graph),
            "gaps": dict(self.gaps),
            "contradictions": dict(self.contradictions),
        }


def _rows(value: Any) -> list[dict[str, Any]]:
    """Coerce a state field to a list of row dicts (``None``/non-list → ``[]``)."""
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    return []


def _property_of(row: Mapping[str, Any]) -> Any:
    """Read a row's property name from ``property_name`` or legacy ``property``."""
    if "property_name" in row:
        return row["property_name"]
    return row.get("property")


def _gap_type(gap: Mapping[str, Any]) -> Any:
    """Read a gap's discriminator from ``type`` or legacy ``kind`` (§13.14)."""
    if "type" in gap:
        return gap["type"]
    return gap.get("kind")


def effect_range(
    experiments: list[dict[str, Any]], property_name: str
) -> tuple[float, float] | None:
    """Return ``(min, max)`` of ``effect`` over rows matching ``property_name``.

    Диапазон эффекта по свойству / effect span for one property: scan every
    experiment row whose property (``property_name`` or legacy ``property``)
    equals ``property_name`` and collect its numeric ``effect`` value. Returns the
    ``(min, max)`` pair, or ``None`` when no row matches or none carries a numeric
    ``effect`` (booleans are rejected — ``bool`` is not a measurement).
    """
    effects: list[float] = []
    for row in experiments:
        if not isinstance(row, Mapping) or _property_of(row) != property_name:
            continue
        effect = row.get("effect")
        if isinstance(effect, bool) or not isinstance(effect, (int, float)):
            continue
        effects.append(float(effect))
    if not effects:
        return None
    return (min(effects), max(effects))


def aggregate_counts(state: dict[str, Any]) -> dict[str, int]:
    """Count experiments, distinct papers and baseline-less gaps for §5.2.2 summary.

    * ``experiments`` — число строк ``retrieved_experiments`` / row count.
    * ``papers`` — distinct ``doc_id`` across ``evidence`` rows (``None`` ignored).
    * ``no_baseline`` — gaps whose type (``type``/``kind``) is ``missing_baseline``.

    Всё считается по plain-dict-полям состояния; отсутствующие поля → 0.
    """
    experiments = _rows(state.get("retrieved_experiments"))
    doc_ids = {
        row["doc_id"] for row in _rows(state.get("evidence")) if row.get("doc_id") is not None
    }
    no_baseline = sum(1 for gap in _rows(state.get("gaps")) if _gap_type(gap) == _MISSING_BASELINE)
    return {
        "experiments": len(experiments),
        "papers": len(doc_ids),
        "no_baseline": no_baseline,
    }


def build_tabs(state: dict[str, Any]) -> AnswerTabs:
    """Assemble the six §5.2.2 answer tabs from agent state (§13.11) fields.

    Раскладка по вкладкам / tab projection: ``summary`` carries the numeric
    :func:`aggregate_counts`; ``experiments`` holds ``retrieved_experiments`` as
    ``rows`` with a ``count`` (== ``len(retrieved_experiments)``); ``evidence``,
    ``gaps`` and ``contradictions`` each hold their rows as ``items`` + ``count``;
    ``graph`` passes the ``visualization_payload`` through as ``payload`` (§5.3).
    Missing state fields collapse to empty rows / zero counts, so all six tabs are
    always present.
    """
    experiments = _rows(state.get("retrieved_experiments"))
    evidence = _rows(state.get("evidence"))
    gaps = _rows(state.get("gaps"))
    contradictions = _rows(state.get("contradictions"))
    viz = state.get("visualization_payload")
    payload = dict(viz) if isinstance(viz, Mapping) else None
    return AnswerTabs(
        summary={"counts": aggregate_counts(state)},
        experiments={"rows": experiments, "count": len(experiments)},
        evidence={"items": evidence, "count": len(evidence)},
        graph={"payload": payload},
        gaps={"items": gaps, "count": len(gaps)},
        contradictions={"items": contradictions, "count": len(contradictions)},
    )
