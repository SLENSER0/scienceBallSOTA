"""Gap-ranking quality eval: nDCG & Spearman vs a golden priority ranking (§15.10 / §18.6).

``gap_metrics.py`` даёт *set-based* precision/recall/F1 — «нашли ли мы нужные пробелы?».
Этот модуль дополняет его *ranking* качеством: насколько порядок предсказанных пробелов
совпадает с золотым ранжированием по приоритету. Две меры:

* **nDCG@k** — normalized Discounted Cumulative Gain по top-k предсказанного порядка против
  идеального (relevance-убывающего) порядка. ``1.0`` — идеальное ранжирование, меньше — хуже.
* **Spearman** — ранговая корреляция позиций (по id, присутствующим и в предсказании, и в
  золотом порядке): ``+1.0`` идентичный порядок, ``-1.0`` полностью обратный.

Ranking model: ``predicted_ids`` — упорядоченный (по убыванию приоритета) список id пробелов;
``gold_relevance`` — id -> релевантность (>=0, отсутствующие id считаются релевантностью ``0``);
``gold_order`` — золотой порядок id по приоритету (для Spearman). Всё pure-stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log2


@dataclass(frozen=True)
class GapRankingScore:
    """Ranking-quality score of a predicted gap ordering (§15.10 / §18.6).

    ``ndcg_at_k`` в ``[0.0, 1.0]`` (nDCG по top-k); ``spearman`` в ``[-1.0, 1.0]`` (ранговая
    корреляция); ``k`` — усечение для nDCG; ``n_matched`` — число id, общих для предсказания
    и ``gold_order`` (участвующих в Spearman).
    """

    ndcg_at_k: float
    spearman: float
    k: int
    n_matched: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "ndcg_at_k": round(self.ndcg_at_k, 4),
            "spearman": round(self.spearman, 4),
            "k": self.k,
            "n_matched": self.n_matched,
        }


def _dcg(rels: list[float]) -> float:
    """Discounted Cumulative Gain: ``sum(rel_i / log2(i + 2))`` по 0-based позициям ``i``."""
    return sum(rel / log2(i + 2) for i, rel in enumerate(rels))


def ndcg_at_k(predicted_ids: list[str], gold_relevance: dict[str, float], k: int = 10) -> float:
    """nDCG@k предсказанного порядка против идеального (relevance-убывающего) порядка.

    Берём top-k предсказанных id, их gains — ``gold_relevance.get(id, 0.0)``. Ideal DCG —
    из top-k наибольших значений ``gold_relevance``. Возвращает ``dcg / idcg``, либо ``0.0``
    если идеальный DCG равен ``0`` (в т.ч. при пустом предсказании).
    """
    if k <= 0 or not predicted_ids:
        return 0.0
    gains = [float(gold_relevance.get(pid, 0.0)) for pid in predicted_ids[:k]]
    dcg = _dcg(gains)
    ideal = sorted((float(v) for v in gold_relevance.values()), reverse=True)[:k]
    idcg = _dcg(ideal)
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def spearman(predicted_ids: list[str], gold_order: list[str]) -> float:
    """Spearman ранговая корреляция позиций по id, общим для обоих порядков.

    Ограничиваемся id, присутствующими и в ``predicted_ids``, и в ``gold_order`` (порядок
    предсказания сохраняется). Ранги — позиции в отфильтрованных списках. Возвращает ``0.0``
    при менее чем двух общих id. Идентичный порядок -> ``+1.0``, обратный -> ``-1.0``.
    """
    gold_set = set(gold_order)
    pred_set = set(predicted_ids)
    common = [pid for pid in predicted_ids if pid in gold_set]
    n = len(common)
    if n < 2:
        return 0.0
    pred_rank = {pid: i for i, pid in enumerate(common)}
    gold_rank = {gid: i for i, gid in enumerate(g for g in gold_order if g in pred_set)}
    d2 = sum((pred_rank[cid] - gold_rank[cid]) ** 2 for cid in common)
    return 1.0 - (6.0 * d2) / (n * (n * n - 1))


def evaluate(
    predicted_ids: list[str],
    gold_relevance: dict[str, float],
    gold_order: list[str],
    k: int = 10,
) -> GapRankingScore:
    """Полная оценка ранжирования пробелов: nDCG@k + Spearman в одном :class:`GapRankingScore`."""
    ndcg = ndcg_at_k(predicted_ids, gold_relevance, k)
    sp = spearman(predicted_ids, gold_order)
    n_matched = len(set(predicted_ids) & set(gold_order))
    return GapRankingScore(ndcg_at_k=ndcg, spearman=sp, k=k, n_matched=n_matched)
