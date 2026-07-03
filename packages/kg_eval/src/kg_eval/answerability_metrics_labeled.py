"""Answerability metrics over gold-labeled absence cells (§25.15).

Pure, deterministic scoring of an absence pipeline's per-cell *verdict* against a
three-way gold *label*. Each row is a mapping ``{"predicted": verdict, "gold":
label}`` where ``gold`` is one of ``genuine_gap`` / ``extraction_miss`` /
``present`` and ``predicted`` is drawn from the §25.11 verdict vocabulary
(``genuine_gap`` / ``possible_miss`` / ``retracted`` / ``abstain`` / ``present``).

Метрики отвечают на вопрос «умеет ли система честно говорить „нет данных“»:

* ``no_data_recall`` — доля истинных ``genuine_gap``, названных ``genuine_gap``.
* ``no_data_precision`` — доля предсказанных ``genuine_gap``, которые и вправду
  ``genuine_gap`` по золоту.
* ``false_gap_rate`` — доля ``extraction_miss``, ошибочно названных ``genuine_gap``
  (система выдумала «дыру» там, где на деле промах извлечения).
* ``no_data_genuine_gap_rate`` — доля «настоящих попаданий» (gold ``genuine_gap``
  и pred ``genuine_gap``) среди всех no-data-золотых ячеек (``genuine_gap`` +
  ``extraction_miss``).

Zero-denominator convention: any undefined ratio collapses to ``0.0`` — so empty
input yields all-zero metrics and ``support == 0``.
"""

from __future__ import annotations

from dataclasses import dataclass

# §25.11 verdict vocabulary (kept for reference / validation callers).
VERDICTS = frozenset({"genuine_gap", "possible_miss", "retracted", "abstain", "present"})
# Gold labels that denote a data-absent cell (§25.15).
NO_DATA_GOLDS = frozenset({"genuine_gap", "extraction_miss"})


@dataclass(frozen=True)
class AnswerabilityMetrics:
    """No-data answerability rates over gold-labeled rows (§25.15).

    Все четыре ставки — числа с плавающей точкой в ``[0.0, 1.0]``; ``support`` —
    число оценённых строк.
    """

    no_data_recall: float
    no_data_precision: float
    false_gap_rate: float
    no_data_genuine_gap_rate: float
    support: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "no_data_recall": self.no_data_recall,
            "no_data_precision": self.no_data_precision,
            "false_gap_rate": self.false_gap_rate,
            "no_data_genuine_gap_rate": self.no_data_genuine_gap_rate,
            "support": self.support,
        }


def no_data_recall(rows: list[dict]) -> float:
    """Fraction of gold ``genuine_gap`` rows predicted ``genuine_gap`` (§25.15)."""
    golds = [r for r in rows if r.get("gold") == "genuine_gap"]
    if not golds:
        return 0.0
    hits = sum(1 for r in golds if r.get("predicted") == "genuine_gap")
    return hits / len(golds)


def no_data_precision(rows: list[dict]) -> float:
    """Fraction of predicted ``genuine_gap`` rows that are gold ``genuine_gap`` (§25.15)."""
    preds = [r for r in rows if r.get("predicted") == "genuine_gap"]
    if not preds:
        return 0.0
    hits = sum(1 for r in preds if r.get("gold") == "genuine_gap")
    return hits / len(preds)


def false_gap_rate(rows: list[dict]) -> float:
    """Fraction of gold ``extraction_miss`` rows wrongly predicted ``genuine_gap`` (§25.15)."""
    golds = [r for r in rows if r.get("gold") == "extraction_miss"]
    if not golds:
        return 0.0
    wrong = sum(1 for r in golds if r.get("predicted") == "genuine_gap")
    return wrong / len(golds)


def no_data_genuine_gap_rate(rows: list[dict]) -> float:
    """Fraction of no-data golds that are correct ``genuine_gap`` hits (§25.15).

    Знаменатель — все no-data-золотые ячейки (``genuine_gap`` + ``extraction_miss``);
    числитель — строки, где и золото, и предсказание суть ``genuine_gap``.
    """
    golds = [r for r in rows if r.get("gold") in NO_DATA_GOLDS]
    if not golds:
        return 0.0
    hits = sum(
        1 for r in golds if r.get("gold") == "genuine_gap" and r.get("predicted") == "genuine_gap"
    )
    return hits / len(golds)


def answerability_metrics(rows: list[dict]) -> AnswerabilityMetrics:
    """Fold gold-labeled ``rows`` into a frozen :class:`AnswerabilityMetrics` (§25.15)."""
    return AnswerabilityMetrics(
        no_data_recall=no_data_recall(rows),
        no_data_precision=no_data_precision(rows),
        false_gap_rate=false_gap_rate(rows),
        no_data_genuine_gap_rate=no_data_genuine_gap_rate(rows),
        support=len(rows),
    )
