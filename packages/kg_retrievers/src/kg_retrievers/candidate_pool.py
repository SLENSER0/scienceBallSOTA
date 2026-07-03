"""§12.19 candidate pool — сбор кандидатов из нескольких каналов в один пул (pure python).

Перед ранжированием гибридный поиск собирает hit'ы из разных источников (dense-вектор,
BM25/keyword, граф-обход, alias-index). Один и тот же чанк часто приходит из нескольких
каналов с разными score. Этот модуль накапливает такие hit'ы и сворачивает их в единый
дедуплицированный пул кандидатов:

- :class:`CandidatePool` — mutable-аккумулятор: :meth:`~CandidatePool.add` кладёт партию
  hit'ов от одного источника; :meth:`~CandidatePool.merged` отдаёт свёрнутый по ``id``
  список :class:`MergedCandidate` — по одному представителю на ``id`` с **максимальным
  score** и множеством вкладывавшихся источников; :meth:`~CandidatePool.sources_of`
  говорит, из каких каналов пришёл конкретный ``id``.
- :class:`MergedCandidate` — frozen-запись результата свёртки (``id``/``score``/``text``/
  ``sources``) с :meth:`~MergedCandidate.as_dict` для сериализации.

Каждый hit — обычный ``dict`` со скалярным ``score`` и полем ``id`` (плюс любые метаданные,
из которых сохраняется ``text``). Вход не мутируется; ties (равный score) → сохраняется
представитель, встреченный раньше. ``sources`` итогового кандидата отсортированы для
детерминизма; итоговый список — по убыванию score, ties → по ``id`` для стабильности.

Pure python — no numpy, no store/graph/DB access: на вход уже прочитанные hit-``dict``.
Kuzu note: custom node props are NOT queryable columns — callers RETURN base columns and
read the rest via ``get_node()`` before assembling the hit dicts fed here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

# §12.19 ключ дедупликации и поля, переносимые в MergedCandidate.
DEFAULT_ID_KEY = "id"
DEFAULT_SCORE_KEY = "score"
DEFAULT_TEXT_KEY = "text"


def _score_of(hit: Mapping[str, Any]) -> float:
    """Extract a hit's relevance score, defaulting to 0.0 if absent/non-numeric (§12.19)."""
    val = hit.get(DEFAULT_SCORE_KEY, 0.0)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


@dataclass(frozen=True)
class MergedCandidate:
    """One deduplicated candidate after pool merge (§12.19).

    ``id`` — ключ дедупликации; ``score`` — максимальный score среди всех вкладов этого
    ``id``; ``text`` — текст представителя с максимальным score; ``sources`` — отсортированный
    ``tuple`` каналов, из которых пришёл ``id`` (immutable → dataclass хешируем).
    """

    id: str
    score: float
    text: str
    sources: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready projection; ``sources`` — список для сериализации (§12.19)."""
        return {
            "id": self.id,
            "score": self.score,
            "text": self.text,
            "sources": list(self.sources),
        }


class CandidatePool:
    """Accumulate hits from many channels, then merge dedup-by-id (§12.19).

    :meth:`add` кладёт партию hit'ов от одного источника (метка ``source``). :meth:`merged`
    сворачивает всё накопленное по ``id``: score = максимум по вкладам, ``text`` — от вклада
    с максимальным score (ties → первый встреченный), ``sources`` — все каналы данного ``id``.
    :meth:`sources_of` возвращает отсортированные источники одного ``id``. Пул mutable; сами
    hit-``dict`` не мутируются.
    """

    def __init__(self) -> None:
        # Порядок первого появления id (для детерминизма при равных score).
        self._order: list[str] = []
        # id -> (best_score, best_text) представителя с максимальным score.
        self._best: dict[str, tuple[float, str]] = {}
        # id -> множество источников, вносивших этот id.
        self._sources: dict[str, set[str]] = {}

    def add(self, source: str, hits: Iterable[Mapping[str, Any]]) -> None:
        """Add a batch of hits from one ``source`` channel (§12.19).

        Каждый hit должен нести ``id``; ``score`` (дефолт 0.0) и ``text`` (дефолт "")
        опциональны. Обновляет представителя ``id``, если у hit score **строго больше**
        текущего (ties → сохраняется ранее встреченный). Регистрирует ``source`` для ``id``.
        """
        for hit in hits:
            cid = hit.get(DEFAULT_ID_KEY)
            if cid is None:
                continue
            cid = str(cid)
            score = _score_of(hit)
            text = str(hit.get(DEFAULT_TEXT_KEY, ""))
            if cid not in self._best:
                self._order.append(cid)
                self._best[cid] = (score, text)
                self._sources[cid] = {source}
            else:
                self._sources[cid].add(source)
                if score > self._best[cid][0]:  # strict → ties keep earlier representative
                    self._best[cid] = (score, text)

    def sources_of(self, cid: str) -> tuple[str, ...]:
        """Sorted channels that contributed ``cid``; empty tuple if unknown (§12.19)."""
        return tuple(sorted(self._sources.get(cid, set())))

    def merged(self) -> list[MergedCandidate]:
        """Dedup-by-id candidates, sorted by score desc, ties → ``id`` asc (§12.19).

        По одному :class:`MergedCandidate` на ``id``: ``score`` — максимум, ``text`` — от
        лучшего вклада, ``sources`` — все каналы. Пустой пул → ``[]``.
        """
        out = [
            MergedCandidate(
                id=cid,
                score=self._best[cid][0],
                text=self._best[cid][1],
                sources=self.sources_of(cid),
            )
            for cid in self._order
        ]
        out.sort(key=lambda c: (-c.score, c.id))
        return out

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready projection of the merged pool (§12.19)."""
        return {"candidates": [c.as_dict() for c in self.merged()]}
