"""Community similarity via Jaccard overlap of member sets (§11.16).

Compares two communities by the Jaccard index of their member id sets and picks
the community most similar to a given target. Pure in-memory computation: it
operates on member-id sets already materialised (e.g. from ``community_id``
groupings), so it does not touch the Kuzu store.

Схожесть сообществ по индексу Жаккара их множеств участников и выбор наиболее
похожего сообщества на заданное. Чистая функция, без обращения к хранилищу.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


def community_similarity(a_members: set[str], b_members: set[str]) -> float:
    """Jaccard index ``|A ∩ B| / |A ∪ B|`` of two member sets (§11.16).

    Returns ``1.0`` for identical sets, ``0.0`` for disjoint ones, and ``0.0``
    when both sets are empty (empty union → no shared structure to reward).
    """
    if not a_members and not b_members:
        return 0.0
    inter = len(a_members & b_members)
    union = len(a_members | b_members)
    return inter / union


@dataclass(frozen=True)
class SimilarityResult:
    """Best match of a target community against a set of candidates (§11.16).

    - ``community_id`` — id of the most similar candidate (``None`` when there
      is no candidate to compare against);
    - ``score`` — its Jaccard similarity to the target (``0.0`` when none).
    """

    community_id: str | None
    score: float

    def as_dict(self) -> dict:
        return {"community_id": self.community_id, "score": self.score}


def most_similar(
    communities: Mapping[str, Iterable[str]],
    target: str,
) -> SimilarityResult:
    """Find the community most similar to ``target`` in ``communities`` (§11.16).

    ``communities`` maps community id → member ids; ``target`` names the entry to
    compare every *other* entry against. The target itself is excluded (a set is
    trivially identical to itself). Ties are broken by ascending community id for
    a stable result. When there is no other community, returns an empty
    :class:`SimilarityResult` (``community_id=None``, ``score=0.0``).
    """
    if target not in communities:
        raise KeyError(f"target community {target!r} not in communities")
    target_members = set(communities[target])
    best_id: str | None = None
    best_score = 0.0
    for cid in sorted(communities):
        if cid == target:
            continue
        score = community_similarity(target_members, set(communities[cid]))
        if best_id is None or score > best_score:
            best_id, best_score = cid, score
    return SimilarityResult(community_id=best_id, score=best_score)
