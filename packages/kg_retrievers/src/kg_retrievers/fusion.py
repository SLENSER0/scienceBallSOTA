"""Spec-exact §12.4/§10.2 fusion: Reciprocal Rank Fusion + weighted linear fusion.

Спец-точный компаньон к :mod:`kg_retrievers.scoring` (тот min-max-нормализует
компоненты — здесь формула §10.2 воспроизводится БУКВАЛЬНО, без нормализации).

Two switchable fusion strategies (§12.4, config-флаг ``fusion.method``):

- :func:`rrf_fuse` — Reciprocal Rank Fusion (§7.5 Node 6): ``score = Σ 1/(k+rank)``
  по позиции id в каждом канале (``rank`` 1-based, лучший = 1).
- :func:`weighted_fuse_v2` — линейная взвешенная сумма строго по §10.2:
  ``score = 0.35*dense + 0.25*sparse + 0.20*bm25 + 0.10*graph_proximity``
  ``+ 0.10*evidence_quality`` (веса — :data:`DEFAULT_FUSION_WEIGHTS`).

:func:`validate_weights` стережёт инвариант §12.4 «сумма весов == 1.0».

Pure python — no store/graph access; callers assemble the ranking/score dicts.
Kuzu note: custom node props are not queryable columns — callers RETURN base
columns and read the rest via ``get_node()`` before building the score dicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# §10.2 canonical channels, in the fixed formula order.
FUSION_CHANNELS: tuple[str, ...] = (
    "dense",
    "sparse",
    "bm25",
    "graph_proximity",
    "evidence_quality",
)

# §10.2 / §12.4 веса по умолчанию: 0.35 dense + 0.25 sparse + 0.20 bm25
# + 0.10 graph_proximity + 0.10 evidence_quality (сумма == 1.0).
DEFAULT_FUSION_WEIGHTS: dict[str, float] = {
    "dense": 0.35,
    "sparse": 0.25,
    "bm25": 0.20,
    "graph_proximity": 0.10,
    "evidence_quality": 0.10,
}

# Default RRF constant (§12.4, config ``rrf_k``).
DEFAULT_RRF_K: int = 60

# Absolute tolerance for the «weights sum to 1.0» check (§12.4).
_WEIGHT_SUM_TOL: float = 1e-6


def validate_weights(weights: dict[str, float]) -> None:
    """Raise ``ValueError`` unless the fusion weights sum to ~1.0 (§12.4).

    Инвариант §12.4: при загрузке конфига сумма весов должна равняться 1.0.
    Допуск — ``abs(sum - 1.0) < 1e-6``; иначе поднимается ошибка.
    """
    if not weights:
        raise ValueError("fusion weights must not be empty")
    total = float(sum(weights.values()))
    if abs(total - 1.0) >= _WEIGHT_SUM_TOL:
        raise ValueError(f"fusion weights must sum to 1.0, got {total!r}")


@dataclass(frozen=True)
class FusedHit:
    """One fused candidate: итоговый ``score`` + покомпонентные ``components`` (§12.4)."""

    id: str
    score: float
    components: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        """Plain-dict projection for UI/debug explainability (§12.4)."""
        return {"id": self.id, "score": self.score, "components": dict(self.components)}


def _first_appearance_order(sources: dict[str, dict[str, float] | list[str]]) -> list[str]:
    """Ids in first-appearance order (source order, then item order) — tie-stable."""
    seen: dict[str, None] = {}
    for items in sources.values():
        for cid in items:  # dict → keys, list → elements
            if cid not in seen:
                seen[cid] = None
    return list(seen)


def rrf_fuse(rankings: dict[str, list[str]], *, k: int = DEFAULT_RRF_K) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion (§7.5 Node 6, §12.4): ``score = Σ 1/(k+rank)``.

    ``rankings`` maps a channel name to an ordered id list (лучший — первым).
    ``rank`` 1-based (лучший = 1); id суммирует вклад из каждого канала, где он
    встречается. Ties сохраняют порядок первого появления (stable). Пусто → ``[]``.
    """
    if k <= 0:
        raise ValueError(f"rrf k must be positive, got {k!r}")
    scores: dict[str, float] = dict.fromkeys(_first_appearance_order(rankings), 0.0)
    for ids in rankings.values():
        for position, cid in enumerate(ids):
            rank = position + 1  # 1-based rank
            scores[cid] += 1.0 / (k + rank)
    # Stable sort: равные score → порядок первого появления сохраняется.
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def weighted_fuse_v2(
    channel_scores: dict[str, dict[str, float]],
    weights: dict[str, float] | None = None,
) -> list[FusedHit]:
    """Linear weighted fusion строго по формуле §10.2 (без нормализации).

    ``channel_scores`` maps a channel name (dense/sparse/bm25/graph_proximity/
    evidence_quality) to ``{id: raw_score}``. Missing channel/id counts as 0
    (dedup across sources, §12.4). ``score = Σ weight[c] * channel_scores[c][id]``
    по ключам весов. Result — :class:`FusedHit` list, ranked desc (stable).
    """
    w = DEFAULT_FUSION_WEIGHTS if weights is None else weights
    out: list[FusedHit] = []
    for cid in _first_appearance_order(channel_scores):
        components = {c: float(channel_scores.get(c, {}).get(cid, 0.0)) for c in w}
        total = sum(w[c] * components[c] for c in w)
        out.append(FusedHit(id=cid, score=total, components=components))
    # Stable sort: равные score → порядок первого появления сохраняется.
    out.sort(key=lambda h: h.score, reverse=True)
    return out
