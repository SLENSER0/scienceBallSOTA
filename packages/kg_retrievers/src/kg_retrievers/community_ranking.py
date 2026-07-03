"""Community-report ranking (§11.19).

Ранжирование отчётов по сообществам (community reports): вычисляет составной
score из нормированного размера сообщества, числа находок (findings) и
собственного поля ``rank`` отчёта, затем сортирует по убыванию score и по
возрастанию ``community_id`` при равенстве.

English: :func:`rank_communities` reads each report's community ``size``, its
findings count and its own ``rank`` field, min-max normalises each metric to
``[0, 1]`` across all reports, and blends them with configurable weights
(default ``{'size': 0.4, 'findings': 0.3, 'rank': 0.3}``) into one score.
Records come back sorted by descending score, ``community_id`` ascending breaking
ties. :func:`top_communities` returns the ``k`` highest-scoring community ids.

Weights are renormalised to sum to ``1.0`` so the blended score always lands in
``[0, 1]`` regardless of the weights passed — a positive rescale that never
changes the ranking order. Pure in-memory transform: reads no store, writes
nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Default blend weights for the composite score (§11.19). Sum to 1.0.
DEFAULT_WEIGHTS: dict[str, float] = {"size": 0.4, "findings": 0.3, "rank": 0.3}

# Score rounding — keeps ``as_dict()`` output stable and free of float noise.
SCORE_NDIGITS = 6


@dataclass(frozen=True)
class CommunityRank:
    """One ranked community report (§11.19).

    - ``community_id`` — the community's integer id;
    - ``level`` — hierarchy level the report belongs to;
    - ``size`` — member count of the community (raw, un-normalised);
    - ``n_findings`` — number of findings in the report;
    - ``rank_field`` — the report's own ``rank`` value, as supplied;
    - ``score`` — composite blend in ``[0, 1]`` of the three normalised metrics.
    """

    community_id: int
    level: int
    size: int
    n_findings: int
    rank_field: float
    score: float

    def as_dict(self) -> dict[str, Any]:
        """JSON shape ``{community_id, level, size, n_findings, rank_field, score}``."""
        return {
            "community_id": self.community_id,
            "level": self.level,
            "size": self.size,
            "n_findings": self.n_findings,
            "rank_field": self.rank_field,
            "score": self.score,
        }


def _coerce_int(value: object, default: int = 0) -> int:
    """Coerce a raw cell to ``int`` (``bool`` and non-numerics fall back to ``default``)."""
    if isinstance(value, bool):  # bool is an int subclass — never a count
        return default
    if isinstance(value, (int, float)):
        return int(value)
    return default


def _coerce_float(value: object, default: float = 0.0) -> float:
    """Coerce a raw cell to ``float`` (``bool`` and non-numerics fall back to ``default``)."""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _findings_count(report: dict[str, Any]) -> int:
    """Findings count: explicit ``n_findings`` if present, else ``len(findings)``."""
    explicit = report.get("n_findings")
    if explicit is not None:
        return _coerce_int(explicit)
    findings = report.get("findings")
    if isinstance(findings, (list, tuple)):
        return len(findings)
    return 0


def _resolve_weights(weights: dict[str, float] | None) -> dict[str, float]:
    """Fill missing keys from the defaults, then renormalise the trio to sum to ``1.0``.

    A non-positive total (all weights zero/negative) falls back to the defaults, so the
    blend is always a proper convex combination.
    """
    if weights is None:
        return dict(DEFAULT_WEIGHTS)
    raw = {key: _coerce_float(weights.get(key, 0.0)) for key in DEFAULT_WEIGHTS}
    total = sum(raw.values())
    if total <= 0.0:
        return dict(DEFAULT_WEIGHTS)
    return {key: value / total for key, value in raw.items()}


def rank_communities(
    reports: list[dict], *, weights: dict[str, float] | None = None
) -> list[CommunityRank]:
    """Rank community reports by a composite of size, findings and their ``rank`` (§11.19).

    Each metric is min-max normalised to ``[0, 1]`` across ``reports`` (divided by its
    maximum; a zero maximum yields ``0.0``), then blended with ``weights`` (renormalised to
    sum to ``1.0``; defaults to ``{'size': 0.4, 'findings': 0.3, 'rank': 0.3}``). Records
    come back sorted by descending score, with ``community_id`` ascending breaking ties.
    Empty input yields ``[]`` (graceful).
    """
    if not reports:
        return []
    resolved = _resolve_weights(weights)
    raw: list[tuple[int, int, int, int, float]] = []
    for report in reports:
        raw.append(
            (
                _coerce_int(report.get("community_id")),
                _coerce_int(report.get("level")),
                _coerce_int(report.get("size")),
                _findings_count(report),
                _coerce_float(report.get("rank")),
            )
        )
    max_size = max((r[2] for r in raw), default=0)
    max_findings = max((r[3] for r in raw), default=0)
    max_rank = max((r[4] for r in raw), default=0.0)

    ranked: list[CommunityRank] = []
    for community_id, level, size, n_findings, rank_field in raw:
        norm_size = size / max_size if max_size > 0 else 0.0
        norm_findings = n_findings / max_findings if max_findings > 0 else 0.0
        norm_rank = rank_field / max_rank if max_rank > 0 else 0.0
        blended = (
            resolved["size"] * norm_size
            + resolved["findings"] * norm_findings
            + resolved["rank"] * norm_rank
        )
        score = max(0.0, min(1.0, blended))
        ranked.append(
            CommunityRank(
                community_id=community_id,
                level=level,
                size=size,
                n_findings=n_findings,
                rank_field=rank_field,
                score=round(score, SCORE_NDIGITS),
            )
        )
    ranked.sort(key=lambda r: (-r.score, r.community_id))
    return ranked


def top_communities(reports: list[dict], k: int) -> list[int]:
    """Return the ``k`` highest-scoring community ids (score-desc, ``id``-asc tie-break).

    ``k <= 0`` (or empty ``reports``) yields ``[]``; ``k`` beyond the report count returns
    every id.
    """
    if k <= 0:
        return []
    return [record.community_id for record in rank_communities(reports)[:k]]
