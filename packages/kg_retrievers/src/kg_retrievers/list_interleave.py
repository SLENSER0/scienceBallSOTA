"""Spec-exact §12.4 **interleaving** fusion: round-robin и team-draft.

Rank-diversity fusion / online A-B eval — чередование ранжированных списков-
источников, а не сложение очков. Отличается от:

* :func:`kg_retrievers.fusion.rrf_fuse` — reciprocal-rank score fusion,
* :func:`kg_retrievers.borda_fusion.borda_fuse` — positional Borda-count,
* :func:`kg_retrievers.lost_in_middle_reorder` — переупаковка одного списка.

Round-robin: колоночный обход источников в порядке вставки — на позиции ``j``
берём ``ranking[j]`` у каждого источника по очереди, глобально дедуплицируя
(первое вхождение выигрывает и запоминается в ``source_of``).

Team-draft: детерминированное чередование двух списков, первым ходит ``list_a``,
уже выбранные id пропускаются (within-list относительный порядок сохраняется).

Pure python — no store/graph access; callers assemble the ranked lists.
Kuzu note: custom node props are not queryable columns — callers RETURN base
columns and read the rest via ``get_node()`` before building the rankings.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class InterleaveResult:
    """Interleaved order + карта ``id -> источник`` (§12.4)."""

    order: tuple[str, ...]
    source_of: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        """Plain-dict projection for UI/debug explainability (§12.4)."""
        return {
            "order": self.order,
            "source_of": self.source_of,
        }


def round_robin(rankings: dict[str, list[str]]) -> InterleaveResult:
    """Round-robin interleave ранжированных списков-источников (§12.4).

    Колоночный обход: для каждой позиции ``j`` перебираем источники в порядке
    вставки и берём ``rankings[source][j]`` (если есть). Глобальный дедуп —
    первое вхождение id выигрывает и фиксирует свой источник в ``source_of``.
    Пустой ``rankings`` -> пустой ``order``. Один источник -> его порядок как есть.
    """
    order: list[str] = []
    source_of: dict[str, str] = {}
    seen: set[str] = set()
    max_len = max((len(ranked) for ranked in rankings.values()), default=0)
    for j in range(max_len):
        for source, ranked in rankings.items():
            if j >= len(ranked):
                continue
            doc_id = ranked[j]
            if doc_id in seen:
                continue
            seen.add(doc_id)
            order.append(doc_id)
            source_of[doc_id] = source
    return InterleaveResult(order=tuple(order), source_of=source_of)


def team_draft(list_a: list[str], list_b: list[str]) -> InterleaveResult:
    """Team-draft interleave двух списков, первым ходит ``list_a`` (§12.4).

    Детерминированно чередуем ходы: на своём ходу команда берёт первый ещё не
    выбранный id из своего списка (already-picked id пропускаются), после чего
    ход переходит другой команде. Если у текущей команды не осталось id, ход
    просто переходит другой. Within-list относительный порядок сохраняется;
    источник фиксируется в ``source_of`` как ``"list_a"`` / ``"list_b"``.
    """
    order: list[str] = []
    source_of: dict[str, str] = {}
    seen: set[str] = set()
    i = j = 0
    turn_a = True
    while i < len(list_a) or j < len(list_b):
        if turn_a:
            while i < len(list_a) and list_a[i] in seen:
                i += 1
            if i < len(list_a):
                doc_id = list_a[i]
                i += 1
                seen.add(doc_id)
                order.append(doc_id)
                source_of[doc_id] = "list_a"
            turn_a = False
        else:
            while j < len(list_b) and list_b[j] in seen:
                j += 1
            if j < len(list_b):
                doc_id = list_b[j]
                j += 1
                seen.add(doc_id)
                order.append(doc_id)
                source_of[doc_id] = "list_b"
            turn_a = True
    return InterleaveResult(order=tuple(order), source_of=source_of)
