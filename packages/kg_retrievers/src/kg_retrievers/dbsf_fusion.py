"""Distribution-Based Score Fusion (DBSF) — §12.4 Weighted fusion / RRF семейство.

Третий нормализующий приём fusion рядом с :mod:`kg_retrievers.fusion`
(weighted + RRF) и :mod:`kg_retrievers.score_normalization` (min-max / z-score):
DBSF нормализует каждый источник по его собственному «3-sigma» окну, а затем
складывает нормализованные вклады по всем источникам.

DBSF нормализация одного источника (§12.4):

- центр окна — среднее (``mean``) → маппится ровно в ``0.5``;
- ширина окна — ``6*std`` (популяционное СКО), т.е. ``[mean-3std, mean+3std]``;
- формула ``(s - (mean - 3*std)) / (6*std)`` с зажимом в ``[0.0, 1.0]``;
- вырожденный источник (``std == 0``) → все значения ``0.5``.

Fusion (§12.4): нормализуем каждый источник независимо, затем суммируем
нормализованные значения по источникам (отсутствие источника → вклад ``0``),
сортируем по убыванию score с лексикографическим tiebreak по ``doc_id``.

Pure python — no store/graph access; caller собирает ``{source: {doc_id: score}}``.
Kuzu note: custom node props are not queryable columns — caller RETURNs base
columns and reads the rest via ``get_node()`` before building the score dicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Any


@dataclass(frozen=True)
class DBSFHit:
    """Один DBSF-кандидат: суммарный ``score`` + вклад каждого источника (§12.4)."""

    doc_id: str
    score: float
    per_source: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict проекция для UI/debug: ``{doc_id, score, per_source}``."""
        return {
            "doc_id": self.doc_id,
            "score": self.score,
            "per_source": dict(self.per_source),
        }


def _dbsf_normalize(scores: dict[str, float]) -> dict[str, float]:
    """DBSF-нормализация одного источника в ``[0,1]`` по окну ``[mean-3std, mean+3std]``.

    Маппинг ``(s - (mean - 3*std)) / (6*std)`` с зажимом в ``[0.0, 1.0]``
    (популяционное СКО). Среднее → ровно ``0.5``; ``mean+3std`` → ``1.0``,
    ``mean-3std`` → ``0.0``. Вырожденный источник (``std == 0``) → все ``0.5``.
    """
    if not scores:
        return {}
    mu = mean(scores.values())
    sigma = pstdev(scores.values())
    if sigma == 0.0:
        return dict.fromkeys(scores, 0.5)
    lo = mu - 3.0 * sigma
    width = 6.0 * sigma
    out: dict[str, float] = {}
    for doc_id, raw in scores.items():
        norm = (float(raw) - lo) / width
        out[doc_id] = min(1.0, max(0.0, norm))
    return out


def dbsf_fuse(scores_by_source: dict[str, dict[str, float]]) -> list[DBSFHit]:
    """Distribution-Based Score Fusion по источникам (§12.4).

    Каждый источник нормализуется независимо через :func:`_dbsf_normalize`,
    затем нормализованные значения суммируются по источникам (отсутствие
    ``doc_id`` в источнике → вклад ``0``). Результат — список :class:`DBSFHit`,
    отсортированный по убыванию ``score`` с лексикографическим tiebreak по
    ``doc_id``. Пустой вход → ``[]``.
    """
    normalized: dict[str, dict[str, float]] = {
        source: _dbsf_normalize(src_scores) for source, src_scores in scores_by_source.items()
    }
    totals: dict[str, float] = {}
    per_source: dict[str, dict[str, float]] = {}
    for source, src_norm in normalized.items():
        for doc_id, value in src_norm.items():
            totals[doc_id] = totals.get(doc_id, 0.0) + value
            per_source.setdefault(doc_id, {})[source] = value
    hits = [
        DBSFHit(doc_id=doc_id, score=totals[doc_id], per_source=per_source[doc_id])
        for doc_id in totals
    ]
    hits.sort(key=lambda h: (-h.score, h.doc_id))
    return hits
