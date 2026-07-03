"""§12.14 dedup retrieval hits — свёртка дублей в финальной выдаче (pure python).

Финальный шаг ранжирования часто содержит один и тот же чанк несколько раз: тот же
``id`` пришёл из двух каналов (dense + BM25), либо два разных чанка несут почти
одинаковый текст (переизданный абзац, зеркальный документ). Этот модуль убирает такие
повторы, оставляя по одному представителю с **наибольшим score**:

- :func:`dedup_hits` — **exact dedup by key** («точная свёртка по ключу»): группирует hit'ы
  по значению ``key`` (по умолчанию ``id``) и оставляет по группе представителя с
  максимальным ``score``. Порядок вывода — порядок первого появления ключа (stable).
- :func:`near_dup_by_text` — **near-duplicate collapse** («свёртка почти-дублей»): считает
  сходство текстов через :class:`difflib.SequenceMatcher` и схлопывает те, чей ratio
  ``>= threshold``, в один кластер, оставляя представителя с максимальным ``score``.

Каждый hit — обычный ``dict`` со скалярным ``score`` плюс ключевые/текстовые поля; на
выход отдаются копии-``dict`` (вход не мутируется). Ties (равный score) → сохраняется
первый по порядку появления представитель.

Pure python — no numpy, no store/graph/DB access: на вход уже прочитанные hit-``dict``.
Kuzu note: custom node props are NOT queryable columns — callers RETURN base columns and
read the rest via ``get_node()`` before assembling the hit dicts fed here.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Mapping
from typing import Any

# Дефолты §12.14: ключ точной свёртки и порог сходства текста для near-dup.
DEFAULT_KEY = "id"
DEFAULT_TEXT_KEY = "text"
DEFAULT_THRESHOLD = 0.9


def _score_of(hit: Mapping[str, Any]) -> float:
    """Extract a hit's relevance score, defaulting to 0.0 if absent/non-numeric (§12.14)."""
    val = hit.get("score", 0.0)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _text_ratio(a: str, b: str) -> float:
    """difflib similarity ratio of two texts in [0,1]; identical → 1.0 (§12.14).

    Shortcut equal strings to avoid the O(n·m) match; otherwise
    :meth:`difflib.SequenceMatcher.ratio` = ``2·M/T`` (M matched chars, T total length).
    """
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def dedup_hits(
    hits: Iterable[Mapping[str, Any]],
    *,
    key: str = DEFAULT_KEY,
) -> list[dict[str, Any]]:
    """Exact dedup keeping the highest-scored hit per ``key`` (§12.14).

    Группирует ``hits`` по значению ``key`` (по умолчанию ``id``) и оставляет в каждой
    группе представителя с максимальным ``score`` (со всеми его метаданными). Порядок
    вывода — порядок **первого появления** ключа во входе (stable): более поздний, но
    более высоко оценённый дубль обновляет представителя, не меняя его позицию. При
    равном ``score`` остаётся первый встреченный (ties → earlier input). Hits с
    отсутствующим/``None`` ключом группируются вместе (под ``None``). Возвращаются
    копии-``dict``; вход не мутируется. Пустой вход → ``[]``.
    """
    rep: dict[Any, dict[str, Any]] = {}
    order: list[Any] = []
    for hit in hits:
        k = hit.get(key)
        if k not in rep:
            rep[k] = dict(hit)
            order.append(k)
        elif _score_of(hit) > _score_of(rep[k]):  # strict → ties keep first
            rep[k] = dict(hit)
    return [rep[k] for k in order]


def near_dup_by_text(
    hits: Iterable[Mapping[str, Any]],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    text_key: str = DEFAULT_TEXT_KEY,
) -> list[dict[str, Any]]:
    """Collapse near-identical text into one highest-scored representative (§12.14).

    Идёт по ``hits`` по порядку; текст каждого (поле ``text_key``) сравнивается с текстом
    уже отобранных представителей через :func:`_text_ratio`. Если ratio с каким-то
    представителем ``>= threshold`` — hit считается почти-дублем и сливается в его кластер:
    представитель заменяется, только если у нового hit ``score`` **строго больше** (позиция
    кластера при этом сохраняется). Иначе hit открывает новый кластер. Сравнение
    «жадное»: берётся первый подходящий представитель по порядку. ``threshold`` — включающая
    граница (``>=``). Возвращаются копии-``dict`` по одному на кластер, в порядке появления
    кластеров; вход не мутируется. Пустой вход → ``[]``.
    """
    kept: list[dict[str, Any]] = []
    for hit in hits:
        text = str(hit.get(text_key, ""))
        match_idx: int | None = None
        for i, rep in enumerate(kept):
            if _text_ratio(text, str(rep.get(text_key, ""))) >= threshold:
                match_idx = i
                break
        if match_idx is None:
            kept.append(dict(hit))
        elif _score_of(hit) > _score_of(kept[match_idx]):  # keep higher-scored representative
            kept[match_idx] = dict(hit)
    return kept
