"""Ranked candidate-list entity-linking metrics: acc@1 / recall@k / MRR / NIL (§23.31/§23.35).

Scores *entity linking* in the ZESHEL/GLADIS sense: each mention arrives with a
ranked list of candidate KB ids, and the task is to place the gold id at (or near)
the top — or to abstain (NIL) when the mention has no KB entry at all. This is
deliberately distinct from ``entity_resolution_eval.py``, which scores pairwise
*clustering* co-membership: there the unit is an unordered pair, here the unit is a
single mention with an *ordered* candidate list and an explicit out-of-KB option.

Каждая запись — ``{gold_id: str | None, ranked: list[str]}``. ``gold_id is None``
означает NIL (правильный ответ отсутствует в KB), а пустой ``ranked`` — это NIL-
предсказание системы. Соответственно:

* NIL-запись считается *правильной* тогда и только тогда, когда ``ranked`` пуст —
  система тоже воздержалась. Такая запись даёт вклад ``1`` в acc@1, recall@k и MRR
  (взаимный ранг ``1.0``); непустой ``ranked`` для NIL — это вклад ``0`` везде.
* acc@1 — доля записей, где ``ranked[0] == gold_id`` (top-1 попадание).
* recall@k — доля записей, где ``gold_id`` встречается среди ``ranked[:k]``.
* MRR — средний обратный ранг первого вхождения ``gold_id`` (``0`` если отсутствует).

``nil_accuracy`` считается только по NIL-записям (``gold_id is None``); при их
отсутствии знаменатель пуст и значение по конвенции ``1.0`` (нечего путать).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class LinkingReport:
    """Entity-linking metrics over a ranked candidate list with NIL (§23.31/§23.35).

    ``n`` и ``n_nil`` — точные целые счётчики (всего записей / из них NIL);
    ``acc_at_1``, ``recall_at_k``, ``mrr`` и ``nil_accuracy`` — доли в ``[0.0, 1.0]``;
    ``k`` — отсечка recall@k, сохранённая для воспроизводимости отчёта.
    """

    n: int
    n_nil: int
    acc_at_1: float
    recall_at_k: float
    mrr: float
    nil_accuracy: float
    k: int

    def as_dict(self) -> dict[str, float | int]:
        """Serialise: integer counts exact, float ratios rounded to 4 dp."""
        return {
            "n": self.n,
            "n_nil": self.n_nil,
            "acc_at_1": round(self.acc_at_1, 4),
            "recall_at_k": round(self.recall_at_k, 4),
            "mrr": round(self.mrr, 4),
            "nil_accuracy": round(self.nil_accuracy, 4),
            "k": self.k,
        }


def _first_rank(ranked: Sequence[str], gold_id: str) -> int:
    """1-based rank of the first ``gold_id`` occurrence in ``ranked``, or ``0`` if absent."""
    for index, candidate in enumerate(ranked):
        if candidate == gold_id:
            return index + 1
    return 0


def evaluate(records: Sequence[dict[str, object]], k: int = 5) -> LinkingReport:
    """acc@1 / recall@k / MRR / NIL-accuracy over ranked candidate lists (§23.31/§23.35).

    Каждая запись — ``{"gold_id": str | None, "ranked": list[str]}``. Для NIL-записи
    (``gold_id is None``) все три ранжирующие метрики трактуют «правильно» как «``ranked``
    пуст»: вклад ``1`` в acc@1/recall@k и обратный ранг ``1.0`` в MRR, иначе ``0``.
    Для обычной записи: acc@1 — ``ranked[0] == gold_id``; recall@k — ``gold_id`` в
    ``ranked[:k]``; MRR — обратный ранг первого вхождения (``0`` если отсутствует).

    Raises:
        ValueError: если ``records`` пуст (нечего оценивать) или ``k < 1``.
    """
    if not records:
        raise ValueError("records must be non-empty")
    if k < 1:
        raise ValueError("k must be >= 1")

    n = len(records)
    n_nil = 0
    nil_correct = 0
    acc_hits = 0
    recall_hits = 0
    mrr_sum = 0.0

    for record in records:
        gold_id = record.get("gold_id")
        ranked = record.get("ranked") or []

        if gold_id is None:  # NIL: correct iff the system also abstained (empty ranked).
            n_nil += 1
            correct = len(ranked) == 0
            nil_correct += int(correct)
            acc_hits += int(correct)
            recall_hits += int(correct)
            mrr_sum += 1.0 if correct else 0.0
            continue

        if ranked and ranked[0] == gold_id:
            acc_hits += 1
        if gold_id in ranked[:k]:
            recall_hits += 1
        rank = _first_rank(ranked, gold_id)
        if rank:
            mrr_sum += 1.0 / rank

    nil_accuracy = nil_correct / n_nil if n_nil else 1.0

    return LinkingReport(
        n=n,
        n_nil=n_nil,
        acc_at_1=acc_hits / n,
        recall_at_k=recall_hits / n,
        mrr=mrr_sum / n,
        nil_accuracy=nil_accuracy,
        k=k,
    )
