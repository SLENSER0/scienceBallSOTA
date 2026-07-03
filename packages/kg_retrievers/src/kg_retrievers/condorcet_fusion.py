"""Spec-exact §12.4 **Condorcet/Copeland** pairwise-majority rank aggregation.

Мажоритарный агрегатор рангов, отличный от positional Borda
(:func:`kg_retrievers.borda_fusion.borda_fuse`), score-based comb_fusion
(:mod:`kg_retrievers.comb_fusion`) и reciprocal-rank
(:func:`kg_retrievers.fusion.rrf_fuse`).

Идея Condorcet/Copeland: для каждой неупорядоченной пары документов ``(a, b)``
считаем, в скольких источниках ``a`` "побеждает" ``b`` — ``a`` присутствует и
(``b`` отсутствует **или** ранг ``a`` строго меньше ранга ``b``). Если ``a``
побеждает ``b`` в строгом большинстве источников, ранжирующих хотя бы один из
двух документов, ``a`` получает победу (``win``), а ``b`` — поражение (``loss``);
ничья не даёт очков никому. Итог сортируется по убыванию ``wins``, затем по
возрастанию ``losses``, затем по ``doc_id``.

Pure python — no store/graph access; callers assemble the rankings dict.
Kuzu note: custom node props are not queryable columns — callers RETURN base
columns and read the rest via ``get_node()`` before building the rankings.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations


@dataclass(frozen=True)
class CondorcetHit:
    """One fused doc: число попарных побед ``wins`` и поражений ``losses`` (§12.4)."""

    doc_id: str
    wins: int
    losses: int

    def as_dict(self) -> dict:
        """Plain-dict projection for UI/debug explainability (§12.4)."""
        return {
            "doc_id": self.doc_id,
            "wins": self.wins,
            "losses": self.losses,
        }


def _rank_maps(rankings: dict[str, list[str]]) -> dict[str, dict[str, int]]:
    """Build per-source ``doc_id -> 0-indexed rank`` lookups (лучший = 0)."""
    return {name: {doc: i for i, doc in enumerate(ranked)} for name, ranked in rankings.items()}


def condorcet_fuse(rankings: dict[str, list[str]]) -> list[CondorcetHit]:
    """Fuse ranked lists via Condorcet/Copeland pairwise majority (§12.4).

    ``rankings`` — ``source_name -> ordered doc_id list`` (лучший первым). Для
    каждой неупорядоченной пары ``(a, b)`` среди источников, ранжирующих хотя бы
    один из документов, считаем победы: ``a`` бьёт ``b``, если ``a`` присутствует и
    (``b`` отсутствует или ранг ``a`` < ранг ``b``). Строгое большинство таких
    побед даёт паре победителю ``+1 win``, проигравшему ``+1 loss``; ничья — ничего.
    Результат сортируется ``wins`` desc, ``losses`` asc, ``doc_id`` asc.
    """
    ranks = _rank_maps(rankings)
    docs = sorted({doc for ranked in rankings.values() for doc in ranked})
    wins: dict[str, int] = dict.fromkeys(docs, 0)
    losses: dict[str, int] = dict.fromkeys(docs, 0)

    for a, b in combinations(docs, 2):
        a_beats = b_beats = relevant = 0
        for rmap in ranks.values():
            a_rank = rmap.get(a)
            b_rank = rmap.get(b)
            if a_rank is None and b_rank is None:
                continue
            relevant += 1
            if a_rank is not None and (b_rank is None or a_rank < b_rank):
                a_beats += 1
            elif b_rank is not None and (a_rank is None or b_rank < a_rank):
                b_beats += 1
        if a_beats * 2 > relevant:
            wins[a] += 1
            losses[b] += 1
        elif b_beats * 2 > relevant:
            wins[b] += 1
            losses[a] += 1

    hits = [CondorcetHit(doc_id=doc, wins=wins[doc], losses=losses[doc]) for doc in docs]
    hits.sort(key=lambda h: (-h.wins, h.losses, h.doc_id))
    return hits
