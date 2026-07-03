"""Cell-level accuracy eval for a predicted coverage matrix vs golden (§15.5/§18.7).

Distinct from the four-way :mod:`kg_eval.absence_verdict_confusion` (§25.15): here every
matrix cell — keyed by ``(material_id, property_id[, regime_id])`` — carries a single
boolean gap flag (``has_gap`` / ``covered``). Мы оцениваем предсказанную матрицу покрытия
против золотой на уровне ячеек: пробел (``has_gap == True`` / ``'absent'``) — это
positive class. Precision/recall/F1 считаются по gap-ячейкам, а ``cell_accuracy`` — доля
совпавших ячеек (и covered, и gap) по объединению всех ключей.

Zero-denominator convention: любое неопределённое отношение (нет предсказанных gap,
нет золотых gap, пустой вход) сворачивается в ``0.0`` и никогда не делит на ноль. Ключ,
присутствующий только в золотой матрице, трактуется как предсказанный ``covered``
(missing predicted cell defaults to covered).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoverageCellScore:
    """Cell-level gap metrics for a coverage matrix (§15.5/§18.7).

    ``gap_precision`` / ``gap_recall`` / ``gap_f1`` — метрики для positive class (gap)
    в диапазоне ``[0.0, 1.0]``; ``cell_accuracy`` — доля совпавших ячеек (covered и gap)
    по объединению ключей; ``n_cells`` — размер этого объединения.
    """

    gap_precision: float
    gap_recall: float
    gap_f1: float
    cell_accuracy: float
    n_cells: int

    def as_dict(self) -> dict[str, float | int]:
        """Serialise all five fields to a JSON-friendly dict."""
        return {
            "gap_precision": self.gap_precision,
            "gap_recall": self.gap_recall,
            "gap_f1": self.gap_f1,
            "cell_accuracy": self.cell_accuracy,
            "n_cells": self.n_cells,
        }


def _safe_ratio(numerator: float, denominator: float) -> float:
    """Return ``numerator / denominator`` or ``0.0`` when the denominator is zero."""
    return numerator / denominator if denominator else 0.0


def _cell_key(cell: dict) -> tuple:
    """Build the identity key ``(material_id, property_id[, regime_id])`` for a cell.

    ``regime_id`` включается в ключ только если оно задано (не ``None``), поэтому ячейки
    без режима и с режимом не пересекаются по ключу.
    """
    material_id = cell.get("material_id")
    property_id = cell.get("property_id")
    regime_id = cell.get("regime_id")
    if regime_id is None:
        return (material_id, property_id)
    return (material_id, property_id, regime_id)


def _has_gap(cell: dict) -> bool:
    """Read the gap flag of a cell.

    Accepts either ``has_gap`` (bool) or the inverse ``covered`` (bool); ``has_gap`` wins
    when both are present. Отсутствие обоих ключей трактуется как ``covered`` (no gap).
    """
    if "has_gap" in cell:
        return bool(cell["has_gap"])
    if "covered" in cell:
        return not bool(cell["covered"])
    return False


def evaluate_coverage(
    predicted_cells: list[dict],
    golden_cells: list[dict],
) -> CoverageCellScore:
    """Score a predicted coverage matrix against golden at the cell level.

    Каждая ячейка ключуется через :func:`_cell_key`. По объединению ключей ячейка
    предсказана ``covered`` по умолчанию, если её нет в ``predicted_cells``. Positive
    class — gap (``has_gap == True``). Возвращаются precision/recall/F1 по gap-ячейкам и
    общая ``cell_accuracy`` (совпадения covered и gap). Пустой вход даёт нулевой счёт с
    ``n_cells == 0``.
    """
    pred_gap: dict[tuple, bool] = {}
    for cell in predicted_cells:
        pred_gap[_cell_key(cell)] = _has_gap(cell)

    gold_gap: dict[tuple, bool] = {}
    for cell in golden_cells:
        gold_gap[_cell_key(cell)] = _has_gap(cell)

    keys = set(pred_gap) | set(gold_gap)
    n_cells = len(keys)

    tp = fp = fn = correct = 0
    for key in keys:
        p = pred_gap.get(key, False)  # missing predicted cell defaults to covered
        g = gold_gap.get(key, False)
        if p == g:
            correct += 1
        if p and g:
            tp += 1
        elif p and not g:
            fp += 1
        elif not p and g:
            fn += 1

    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    f1 = _safe_ratio(2 * precision * recall, precision + recall)
    cell_accuracy = _safe_ratio(correct, n_cells)

    return CoverageCellScore(
        gap_precision=precision,
        gap_recall=recall,
        gap_f1=f1,
        cell_accuracy=cell_accuracy,
        n_cells=n_cells,
    )
