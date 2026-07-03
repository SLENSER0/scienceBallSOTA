"""Spec-точная §12.4 семья score-combination фьюзеров Fox & Shaw.

Отдельно от :mod:`kg_retrievers.fusion` (там — взвешенная линейная сумма §10.2
и RRF §7.5). Здесь — классические комбинации оценок Fox & Shaw (TREC-2):

- **CombSUM**  — сумма нормализованных оценок по всем спискам.
- **CombMNZ**  — ``CombSUM * hit_count`` (число списков, содержащих документ).
- **CombANZ**  — ``CombSUM / hit_count`` (средняя ненулевая оценка).
- **CombMED**  — медиана нормализованных оценок документа.

Каждый входной список сначала min-max-нормализуется в ``[0, 1]`` независимо
(:func:`_minmax_per_list`), поэтому шкалы разных каналов сопоставимы.

Pure python — no store/graph access; caller собирает словари ранжирований.
Kuzu note: custom node props не являются queryable-колонками — caller делает
``RETURN`` по базовым колонкам и читает остальное через ``get_node()`` до сборки
словарей оценок; тесты строят временный store при необходимости.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

# §12.4 поддерживаемые методы score-combination (Fox & Shaw).
COMB_METHODS: tuple[str, ...] = ("combsum", "combmnz", "combanz", "combmed")


@dataclass(frozen=True)
class CombResult:
    """Одна строка фьюзинга §12.4: документ + итоговая оценка и разбивка.

    Атрибуты:
        doc_id:     идентификатор документа.
        score:      итоговая оценка выбранного метода.
        hit_count:  число входных списков, содержащих документ.
        per_source: нормализованные ``[0, 1]`` оценки по каждому списку-источнику.
    """

    doc_id: str
    score: float
    hit_count: int
    per_source: dict[str, float]

    def as_dict(self) -> dict:
        """Round-trip всех 4 полей в обычный ``dict`` (для JSON/логов)."""
        return {
            "doc_id": self.doc_id,
            "score": self.score,
            "hit_count": self.hit_count,
            "per_source": dict(self.per_source),
        }


def _minmax_per_list(scores: dict[str, float]) -> dict[str, float]:
    """Min-max-нормализовать один список оценок в ``[0, 1]`` (§12.4).

    Пустой список → пустой словарь. Если все значения равны (``max == min``),
    возвращаем 0.0 для каждого документа (нет разброса — нечего ранжировать).
    """
    if not scores:
        return {}
    values = list(scores.values())
    lo, hi = min(values), max(values)
    span = hi - lo
    if span <= 0.0:
        return dict.fromkeys(scores, 0.0)
    return {doc_id: (value - lo) / span for doc_id, value in scores.items()}


def comb_fuse(
    rankings: dict[str, dict[str, float]],
    *,
    method: str = "combsum",
) -> list[CombResult]:
    """Score-combination фьюзинг §12.4 (Fox & Shaw) по нескольким спискам.

    Каждый список ``rankings[source]`` min-max-нормализуется независимо, затем
    оценки одного документа комбинируются согласно ``method``:

    - ``combsum`` — сумма нормализованных оценок;
    - ``combmnz`` — ``CombSUM * hit_count``;
    - ``combanz`` — ``CombSUM / hit_count``;
    - ``combmed`` — медиана нормализованных оценок документа.

    Возвращает список :class:`CombResult`, отсортированный по ``score`` убыв.,
    затем по ``doc_id`` возр. Неизвестный ``method`` → ``ValueError``.
    """
    method_key = method.lower()
    if method_key not in COMB_METHODS:
        raise ValueError(f"unknown fusion method {method!r}; expected one of {COMB_METHODS}")

    # Нормализуем каждый список отдельно и собираем per-source разбивку по документам.
    normalized = {source: _minmax_per_list(scores) for source, scores in rankings.items()}
    per_source: dict[str, dict[str, float]] = {}
    for source, scores in normalized.items():
        for doc_id, value in scores.items():
            per_source.setdefault(doc_id, {})[source] = value

    results: list[CombResult] = []
    for doc_id, sources in per_source.items():
        norm_values = list(sources.values())
        comb_sum = float(sum(norm_values))
        hit_count = len(norm_values)
        if method_key == "combsum":
            score = comb_sum
        elif method_key == "combmnz":
            score = comb_sum * hit_count
        elif method_key == "combanz":
            score = comb_sum / hit_count if hit_count else 0.0
        else:  # combmed
            score = float(median(norm_values))
        results.append(
            CombResult(
                doc_id=doc_id,
                score=score,
                hit_count=hit_count,
                per_source=dict(sources),
            )
        )

    results.sort(key=lambda item: (-item.score, item.doc_id))
    return results
