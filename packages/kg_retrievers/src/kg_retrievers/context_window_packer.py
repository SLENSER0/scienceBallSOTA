"""Greedy token-budget packing of retrieval hits into an LLM context window (§12.11/§18).

RU: Жадная упаковка хитов ретрива под токен-бюджет контекстного окна LLM (§18
«Медленный чат» / лимиты контекста). Существующие ссылки на ``token_budget``
специфичны для отчётов сообществ; общего упаковщика хитов не было
(``candidate_budget`` распределяет счётчики по источникам, ``snippet_window``
извлекает спаны). :func:`pack` сортирует хиты по убыванию ``score`` (стабильно),
жадно добавляет каждый хит, чей ``token_count`` ещё влезает в остаток бюджета,
и ПРОПУСКАЕТ (не останавливается на) слишком большие хиты, чтобы меньшие
последующие хиты могли заполнить окно.
EN: Greedy token-budget packing of retrieval hits into an LLM context window (§18
'Slow chat' / context limits). The existing ``token_budget`` references are
community-report specific; no general hit packer existed (``candidate_budget``
allocates per-source counts, ``snippet_window`` extracts spans). :func:`pack`
sorts hits by ``score`` descending (stable), greedily adds each hit whose
``token_count`` still fits the remaining budget, and SKIPS (does not stop at)
oversized hits so smaller later hits can still fill the window.

Pure python — no store access. Kuzu note: custom node props are NOT queryable
columns; callers RETURN base columns and read the rest (``token_count``/``score``)
via ``get_node()`` before handing hit dicts to :func:`pack`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PackResult:
    """Frozen result of :func:`pack` (§12.11).

    ``selected_ids`` are the hit ids kept (in score-desc, input-stable order);
    ``used_tokens`` is their summed ``token_count`` (always ``<= budget``);
    ``dropped_ids`` is exactly the complement of ``selected_ids`` (in input order);
    ``budget`` echoes the token budget the packing targeted.
    """

    selected_ids: tuple[str, ...]
    used_tokens: int
    dropped_ids: tuple[str, ...]
    budget: int

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict projection for trace / round-trip (§12.11, house style)."""
        return {
            "selected_ids": self.selected_ids,
            "used_tokens": self.used_tokens,
            "dropped_ids": self.dropped_ids,
            "budget": self.budget,
        }


def pack(
    hits: list[dict],
    budget: int,
    token_key: str = "token_count",
    score_key: str = "score",
) -> PackResult:
    """Greedily pack ``hits`` into ``budget`` tokens by descending score (§12.11).

    RU: Хиты сортируются по убыванию ``score`` (стабильно — при равных счётах
    сохраняется входной порядок). Затем каждый хит добавляется, если его
    ``token_count`` влезает в остаток бюджета; иначе он ПРОПУСКАЕТСЯ (continue),
    а не прерывает цикл, чтобы меньшие последующие хиты могли заполнить окно.
    EN: Hits are sorted by ``score`` descending (stable — equal scores keep input
    order). Each hit is then added if its ``token_count`` fits the remaining
    budget; otherwise it is SKIPPED (continue), not a break, so smaller later
    hits can still fill the window.

    ``used_tokens`` never exceeds ``budget``; ``dropped_ids`` is exactly the
    complement of ``selected_ids``, listed in original input order.
    """
    ranked = sorted(
        enumerate(hits),
        key=lambda pair: (-pair[1].get(score_key, 0), pair[0]),
    )

    selected_ids: list[str] = []
    selected_index: set[int] = set()
    used = 0
    remaining = budget
    for idx, hit in ranked:
        cost = int(hit.get(token_key, 0))
        if cost <= remaining:
            selected_ids.append(str(hit["id"]))
            selected_index.add(idx)
            used += cost
            remaining -= cost

    dropped_ids = tuple(str(hit["id"]) for idx, hit in enumerate(hits) if idx not in selected_index)
    return PackResult(
        selected_ids=tuple(selected_ids),
        used_tokens=used,
        dropped_ids=dropped_ids,
        budget=budget,
    )
