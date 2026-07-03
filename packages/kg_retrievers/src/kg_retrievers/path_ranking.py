"""Rank graph paths by evidence and length (§8.14, pure python).

Ранжирование путей в графе (*graph paths*) — упорядочивает пути (цепочки узлов,
соединённые рёбрами) по совокупной «полезности»: **короткие** пути и пути с
**бо́льшим объёмом эвиденса** (evidence) ценятся выше. Модуль ничего не читает из
графа — на вход уже собранные пути-``dict``.

English: :func:`rank_paths` scores every path and returns them sorted best-first.
Each path contributes two bounded sub-scores that are blended into one final
``score`` in ``[0, 1]``::

    length_score(length)     = 1 / (1 + length)          # fewer edges -> higher
    evidence_score(evidence) = evidence / (1 + evidence)  # more evidence -> higher
    score = LENGTH_WEIGHT * length_score + EVIDENCE_WEIGHT * evidence_score

``length`` is the number of **edges** (``len(nodes) - 1``, floored at 0). The two
weights sum to 1.0, so ``score`` never leaves ``[0, 1]``. :func:`best_path` returns
the single top-ranked path (``None`` for an empty input).

Each input path is a ``Mapping`` with ``nodes`` (a sequence of node ids) and either
``evidence_count`` (an int, wins if present) or ``evidence`` (a collection whose size
is counted). Ties on ``score`` break by shorter ``length``, then more evidence, then
the ``nodes`` tuple — a stable, deterministic order. The input is never mutated.

Pure python — no numpy, no store/graph/DB access. Kuzu note: custom node props are
NOT queryable columns — callers RETURN base columns and read the rest via
``get_node()`` before assembling the path dicts fed here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

# Score weights (§8.14): length and evidence contribute equally; sum == 1.0 keeps [0,1].
LENGTH_WEIGHT = 0.5
EVIDENCE_WEIGHT = 0.5

# Score rounding — keeps ``as_dict()`` output stable and free of float noise.
SCORE_NDIGITS = 6


@dataclass(frozen=True)
class RankedPath:
    """One scored graph path (§8.14).

    ``nodes`` is the ordered tuple of node ids; ``length`` is the edge count
    (``len(nodes) - 1``, floored at 0); ``evidence_count`` is how many evidence items
    back the path; ``score`` blends short-length and high-evidence into ``[0, 1]``.
    """

    nodes: tuple[str, ...]
    length: int
    score: float
    evidence_count: int

    def as_dict(self) -> dict[str, Any]:
        """JSON shape ``{nodes, length, score, evidence_count}`` (``nodes`` as a list)."""
        return {
            "nodes": list(self.nodes),
            "length": self.length,
            "score": self.score,
            "evidence_count": self.evidence_count,
        }


def _nodes_of(path: Mapping[str, Any]) -> tuple[str, ...]:
    """Node ids of a path as a ``str`` tuple (missing/odd ``nodes`` -> empty tuple)."""
    raw = path.get("nodes")
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, Iterable):
        return tuple(str(node) for node in raw)
    return ()


def _evidence_count_of(path: Mapping[str, Any]) -> int:
    """Evidence tally for a path (§8.14).

    An explicit ``evidence_count`` wins when present (coerced to a non-negative int);
    otherwise the size of an ``evidence`` collection is counted. Anything unusable -> 0.
    """
    if "evidence_count" in path:
        try:
            return max(0, int(path["evidence_count"]))
        except (TypeError, ValueError):
            return 0
    evidence = path.get("evidence")
    if isinstance(evidence, list | tuple | set | frozenset):
        return len(evidence)
    return 0


def _length_score(length: int) -> float:
    """Shorter-is-better factor in ``(0, 1]``: ``1 / (1 + length)`` (§8.14)."""
    return 1.0 / (1.0 + length)


def _evidence_score(evidence_count: int) -> float:
    """More-is-better factor in ``[0, 1)``: ``e / (1 + e)`` (§8.14)."""
    return evidence_count / (1.0 + evidence_count)


def _score_path(path: Mapping[str, Any]) -> RankedPath:
    """Turn one raw path ``Mapping`` into a scored :class:`RankedPath` (§8.14)."""
    nodes = _nodes_of(path)
    length = max(0, len(nodes) - 1)
    evidence_count = _evidence_count_of(path)
    score = LENGTH_WEIGHT * _length_score(length) + EVIDENCE_WEIGHT * _evidence_score(
        evidence_count
    )
    return RankedPath(
        nodes=nodes,
        length=length,
        score=round(score, SCORE_NDIGITS),
        evidence_count=evidence_count,
    )


def rank_paths(paths: Iterable[Mapping[str, Any]]) -> list[RankedPath]:
    """Rank ``paths`` best-first by blended length/evidence score (§8.14).

    Scores every path with ``score = LENGTH_WEIGHT * 1/(1+length) + EVIDENCE_WEIGHT *
    evidence/(1+evidence)`` and returns them sorted by **descending** ``score``. Ties
    break by shorter ``length``, then more evidence, then the ``nodes`` tuple — a stable,
    deterministic order. The input is never mutated. An empty input yields ``[]``.
    """
    ranked = [_score_path(path) for path in paths]
    ranked.sort(key=lambda p: (-p.score, p.length, -p.evidence_count, p.nodes))
    return ranked


def best_path(paths: Iterable[Mapping[str, Any]]) -> RankedPath | None:
    """The single top-ranked path (§8.14), or ``None`` when ``paths`` is empty.

    Equivalent to the first element of :func:`rank_paths` — same scoring and tie-break.
    """
    ranked = rank_paths(paths)
    return ranked[0] if ranked else None
