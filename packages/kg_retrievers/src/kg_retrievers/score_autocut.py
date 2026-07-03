"""Spec-exact §12.4 dynamic **autocut** for fusion / rerank candidate tails.

Динамический выбор ``top-k`` по излому (knee) / разрыву (gap) в убывающем списке
скорингов — чтобы fusion/rerank обрезали хвост кандидатов адаптивно, а не по
фиксированному ``top_n``. Ничего похожего в пакете нет.

Соглашение о :class:`CutPoint`: ``index`` — позиция **первого отброшенного**
элемента (0-indexed), ``kept`` — сколько элементов сохранено. Для убывающего
входа всегда ``index == kept`` (обрезается непрерывный хвост).

Pure python — no store/graph access; caller passes an already-descending list.
Kuzu note: custom node props are not queryable columns — callers RETURN base
columns and read the rest via ``get_node()`` before scoring/cutting.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CutPoint:
    """Where a descending score list is cut (§12.4).

    ``index`` — первая отброшенная позиция, ``kept`` — число сохранённых,
    ``gap`` — абсолютный разрыв на границе среза (``0.0`` если ничего не режется),
    ``reason`` — метод, породивший срез (``'gap'`` | ``'threshold'``).
    """

    index: int
    kept: int
    gap: float
    reason: str

    def as_dict(self) -> dict:
        """Plain-dict projection for UI/debug explainability (§12.4)."""
        return {
            "index": self.index,
            "kept": self.kept,
            "gap": self.gap,
            "reason": self.reason,
        }


def largest_gap_cut(scores: Sequence[float], *, min_keep: int = 1) -> CutPoint:
    """Cut after the biggest absolute adjacent drop (§12.4).

    Среди границ ``k`` (сохранить ``k``, отбросить хвост с позиции ``k``) с
    ``k >= min_keep`` выбирается та, где ``scores[k-1] - scores[k]`` максимален.
    Всегда режется хотя бы один элемент, кроме случая, когда сохранить нечего или
    длина не превышает ``min_keep``.
    """
    n = len(scores)
    keep_floor = max(1, min_keep)
    if n == 0:
        return CutPoint(index=0, kept=0, gap=0.0, reason="gap")
    if n <= keep_floor:
        return CutPoint(index=n, kept=n, gap=0.0, reason="gap")
    best_k = keep_floor
    best_gap = float("-inf")
    for k in range(keep_floor, n):
        gap = float(scores[k - 1]) - float(scores[k])
        if gap > best_gap:
            best_gap = gap
            best_k = k
    return CutPoint(index=best_k, kept=best_k, gap=max(best_gap, 0.0), reason="gap")


def relative_threshold_cut(
    scores: Sequence[float],
    *,
    ratio: float = 0.5,
    min_keep: int = 1,
) -> CutPoint:
    """Keep the leading run of scores ``>= top_score * ratio`` (§12.4).

    Сохраняются подряд идущие с начала элементы не ниже ``scores[0] * ratio``.
    ``min_keep`` поднимает результат до как минимум ``min_keep`` (но не выше длины),
    даже если это удерживает элемент ниже порога.
    """
    n = len(scores)
    keep_floor = max(1, min_keep)
    if n == 0:
        return CutPoint(index=0, kept=0, gap=0.0, reason="threshold")
    threshold = float(scores[0]) * ratio
    kept = 0
    for value in scores:
        if float(value) >= threshold:
            kept += 1
        else:
            break
    kept = min(max(kept, keep_floor), n)
    gap = float(scores[kept - 1]) - float(scores[kept]) if kept < n else 0.0
    return CutPoint(index=kept, kept=kept, gap=gap, reason="threshold")


def autocut(scores: Sequence[float], *, method: str = "gap", **kw) -> CutPoint:
    """Dispatch to the named autocut ``method`` (§12.4).

    ``method='gap'`` → :func:`largest_gap_cut`, ``method='threshold'`` →
    :func:`relative_threshold_cut`. Неизвестный метод — ``ValueError``.
    Дополнительные kwargs (``min_keep``, ``ratio``) проброшены в метод.
    """
    if method == "gap":
        return largest_gap_cut(scores, **kw)
    if method == "threshold":
        return relative_threshold_cut(scores, **kw)
    raise ValueError(f"unknown autocut method: {method!r}")
