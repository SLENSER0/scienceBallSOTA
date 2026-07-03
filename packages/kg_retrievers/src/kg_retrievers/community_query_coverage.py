"""Query-entity coverage per community for local-vs-global routing (§11.7/§11.8).

Given the query entities extracted from a question and the member entities of each
Leiden community, this module measures how many query entities each community
covers. High single-community coverage favours a *local* (community-scoped) answer;
low, spread-out coverage favours a *global* map-reduce over community reports.

По множеству сущностей запроса и участникам каждого сообщества вычисляет долю
покрытия сущностей запроса каждым сообществом (маршрутизация local-vs-global).

Coverage rules:
- ``coverage`` — ``len(covered) / len(query_entities)`` in ``[0, 1]``;
- only communities sharing at least one query entity are returned;
- results sort by ``coverage`` descending, then ``community_id`` ascending.

Pure, read-only data logic — no store access.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CommunityCoverage:
    """Query-entity coverage of one community (§11.7/§11.8).

    - ``community_id`` — id of the community;
    - ``level`` — hierarchy level of the community;
    - ``covered`` — sorted tuple of query entities present in this community;
    - ``coverage`` — ``len(covered) / len(query_entities)`` in ``[0, 1]``;
    - ``size`` — number of member entities in this community.
    """

    community_id: int
    level: int
    covered: tuple[str, ...]
    coverage: float
    size: int

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly mapping of this coverage entry."""
        return {
            "community_id": self.community_id,
            "level": self.level,
            "covered": list(self.covered),
            "coverage": self.coverage,
            "size": self.size,
        }


def coverage_by_community(
    query_entities: Sequence[str],
    members_by_community: Mapping[tuple[int, int], Iterable[str]],
    *,
    level: int | None = None,
) -> list[CommunityCoverage]:
    """Coverage of ``query_entities`` by each community in ``members_by_community``.

    ``members_by_community`` maps ``(community_id, level)`` to that community's member
    entities. One :class:`CommunityCoverage` is returned per community sharing at least
    one query entity; when ``level`` is given, only communities at that level count.

    Results sort by ``coverage`` descending, then ``community_id`` ascending; the
    ``covered`` tuple is sorted. Empty ``query_entities`` yields ``[]``.
    """
    query_set = set(query_entities)
    n_query = len(query_set)
    if n_query == 0:
        return []

    results: list[CommunityCoverage] = []
    for (community_id, comm_level), members in members_by_community.items():
        if level is not None and comm_level != level:
            continue
        member_list = list(members)
        covered = query_set & set(member_list)
        if not covered:
            continue
        results.append(
            CommunityCoverage(
                community_id=community_id,
                level=comm_level,
                covered=tuple(sorted(covered)),
                coverage=len(covered) / n_query,
                size=len(member_list),
            )
        )

    results.sort(key=lambda c: (-c.coverage, c.community_id))
    return results


def best_community(
    query_entities: Sequence[str],
    members_by_community: Mapping[tuple[int, int], Iterable[str]],
    *,
    level: int | None = None,
) -> CommunityCoverage | None:
    """Return the highest-coverage community, or ``None`` if none overlap.

    Delegates to :func:`coverage_by_community` and returns its top entry, which is the
    community with the greatest coverage (ties broken by lower ``community_id``).
    """
    ranked = coverage_by_community(query_entities, members_by_community, level=level)
    return ranked[0] if ranked else None
