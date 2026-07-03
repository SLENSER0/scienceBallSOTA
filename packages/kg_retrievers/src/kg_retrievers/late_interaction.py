"""§12.3 Mode B — late-interaction (ColBERT-style) MaxSim rescoring.

Гибридный семантический поиск §12.3 допускает опциональный *multivector /
late-interaction* путь: вместо одного плотного вектора на документ хранится
набор пер-токенных векторов, а близость запрос-документ считается через
**MaxSim** — для каждого токена запроса берётся его максимальная косинусная
близость к любому токену документа, и эти максимумы суммируются (ColBERT,
Khattab & Zaharia 2020). Это «поздняя интеракция»: токены сравниваются попарно
уже после кодирования, что даёт более тонкое сопоставление, чем один вектор.

Здесь — чистый, без зависимостей, референс: :func:`maxsim` считает MaxSim по
двум спискам пер-токенных векторов, а :func:`rescore` применяет его к словарю
кандидатов ``{hit_id: doc_vectors}`` и возвращает :class:`LateInteractionScore`,
отсортированные по убыванию MaxSim. Косинусная близость нормируется на длины
векторов; вектор нулевой нормы (zero-norm, вырожденный) вносит вклад ``0.0`` —
он не совпадает ни с чем. ``token_hits`` считает токены запроса, у которых
лучшее совпадение строго положительно (полезно для отладки: сколько токенов
запроса вообще «зацепились» за документ).

Pure python — no store/graph/DB access: на вход уже готовые векторы. Kuzu note:
custom node props are NOT queryable columns — вызывающий RETURN-ит базовые
колонки и читает пер-токенные векторы через ``get_node`` до передачи сюда.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LateInteractionScore:
    """MaxSim-оценка одного кандидата (§12.3 multivector / late-interaction).

    ``hit_id`` — идентификатор документа; ``maxsim`` — сумма пер-токенных
    максимумов косинусной близости (>= 0.0); ``token_hits`` — число токенов
    запроса, чьё лучшее совпадение строго положительно.
    """

    hit_id: str
    maxsim: float
    token_hits: int

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready projection (§12.3)."""
        return {
            "hit_id": self.hit_id,
            "maxsim": self.maxsim,
            "token_hits": self.token_hits,
        }


def _cosine(a: list[float], b: list[float]) -> float:
    """Косинусная близость двух векторов; zero-norm -> ``0.0`` (§12.3)."""
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=False):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def maxsim(query_vectors: list[list[float]], doc_vectors: list[list[float]]) -> float:
    """Сумма пер-токенных максимумов косинусной близости (ColBERT MaxSim, §12.3).

    Для каждого токена запроса берётся максимум косинусной близости к любому
    токену документа; максимумы суммируются. Пустой ``doc_vectors`` (или пустой
    запрос) -> ``0.0``; zero-norm векторы вносят ``0.0``.
    """
    if not query_vectors or not doc_vectors:
        return 0.0
    total = 0.0
    for q in query_vectors:
        best = 0.0
        for d in doc_vectors:
            sim = _cosine(q, d)
            if sim > best:
                best = sim
        total += best
    return total


def rescore(
    query_vectors: list[list[float]],
    docs: dict[str, list[list[float]]],
    top_n: int | None = None,
) -> list[LateInteractionScore]:
    """MaxSim-рескоринг кандидатов, отсортированный по убыванию (§12.3).

    ``docs`` — ``{hit_id: doc_vectors}``. Для каждого кандидата считается
    :func:`maxsim` и число «зацепившихся» токенов запроса (``token_hits`` —
    лучшее совпадение строго > 0). Результат сортируется по ``maxsim`` убыв.,
    ничьи — по ``hit_id`` для детерминизма; ``top_n`` усекает выдачу.
    """
    scores: list[LateInteractionScore] = []
    for hit_id, doc_vectors in docs.items():
        total = 0.0
        hits = 0
        if query_vectors and doc_vectors:
            for q in query_vectors:
                best = 0.0
                for d in doc_vectors:
                    sim = _cosine(q, d)
                    if sim > best:
                        best = sim
                total += best
                if best > 0.0:
                    hits += 1
        scores.append(LateInteractionScore(hit_id=hit_id, maxsim=total, token_hits=hits))
    scores.sort(key=lambda s: (-s.maxsim, s.hit_id))
    if top_n is not None:
        scores = scores[:top_n]
    return scores
