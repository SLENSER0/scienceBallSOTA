"""GraphRAG map-step candidate selection under a token budget (§11.7).

Global search (глобальный поиск) does *not* send every community report to the LLM.
The pipeline first does vector-retrieval over community summaries, then runs map-reduce
over the *selected* reports ("сначала vector-retrieval community summaries, затем
map-reduce выбранных отчётов"). This module is the fusion pre-filter that sits between
those two stages: given scored community reports, it greedily keeps the highest-scoring
ones that fit a token budget and a report cap, and marks the rest as skipped.

Unlike ``graphrag_cost_estimate`` (which only totals the cost of a fixed set of reports)
and ``graphrag_map_reduce`` (which performs the reduce fold), this module *chooses* which
reports enter the map step at all.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class MapSelection:
    """Outcome of a map-step candidate selection (§11.7).

    ``selected`` — community_ids fed to the map step, best score first;
    ``skipped`` — community_ids left out (over budget or past ``max_reports``), in the
    same score-sorted order; ``used_tokens`` — summed ``est_tokens`` of ``selected``
    (always ``<= budget``); ``budget`` — the token budget the selection was made under.
    """

    selected: tuple[str, ...]
    skipped: tuple[str, ...]
    used_tokens: int
    budget: int

    def as_dict(self) -> dict:
        return {
            "selected": list(self.selected),
            "skipped": list(self.skipped),
            "used_tokens": self.used_tokens,
            "budget": self.budget,
        }


def select_candidates(
    reports: Sequence[Mapping],
    token_budget: int,
    max_reports: int,
) -> MapSelection:
    """Greedily pick the top-scoring reports that fit ``token_budget`` (§11.7).

    Reports are sorted by ``score`` descending, ties broken by ``community_id`` ascending.
    Walking that order, a report's ``community_id`` is added to ``selected`` while the
    running total of ``est_tokens`` stays ``<= token_budget`` and fewer than
    ``max_reports`` have been chosen; otherwise it is skipped. Selection is greedy by
    score: a report whose ``est_tokens`` would overflow the budget is skipped and the walk
    continues, so a later, smaller report can still be taken (жадный отбор по оценке).
    Every ``community_id`` lands in exactly one of ``selected`` / ``skipped``; an empty
    ``reports`` yields ``selected == ()`` and ``used_tokens == 0``.
    """
    ordered = sorted(
        reports,
        key=lambda r: (-r["score"], r["community_id"]),
    )

    selected: list[str] = []
    skipped: list[str] = []
    used_tokens = 0

    for report in ordered:
        community_id = report["community_id"]
        est_tokens = report["est_tokens"]
        if len(selected) < max_reports and used_tokens + est_tokens <= token_budget:
            selected.append(community_id)
            used_tokens += est_tokens
        else:
            skipped.append(community_id)

    return MapSelection(
        selected=tuple(selected),
        skipped=tuple(skipped),
        used_tokens=used_tokens,
        budget=token_budget,
    )
