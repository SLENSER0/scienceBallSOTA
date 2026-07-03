"""``route_after_plan`` — QueryPlan retrieval-strategy → §7.2 ROUTE branch router.

Node ``ROUTE`` of the §7.2 retrieval graph fans a :class:`QueryPlan`'s chosen
``retrieval_strategy`` list out onto the concrete branch graph-nodes that will
actually run. This is *distinct* from
:func:`agent_service.intent_classifier.route_after_classify`, which returns an
ordered plan of **tool** names for Node 2 (classify). Here we map **retrieval
strategies** onto **branch node** names — one hop closer to the executor.

Стратегия → ветвь / strategy → branch (§7.2 ROUTE):

* ``cypher_template`` / ``graph_algo``      → ``structured_retrieval``
* ``hybrid_chunks``   / ``evidence_lookup`` → ``hybrid_retrieval``
* ``graphrag_community``                    → ``graphrag_search``
* ``gap_scan``                              → ``gap_analyzer``

Several strategies collapse onto one branch (structured, hybrid), so the router
**de-duplicates** while preserving first-seen order — a multi-strategy plan
never runs the same branch twice. Unknown strategies are silently skipped
(forward-compatible with new §7.2 plans), and an empty / all-unknown plan
degrades gracefully to the single ``hybrid_retrieval`` fallback so ROUTE always
yields at least one runnable branch (маршрут никогда не пуст).
"""

from __future__ import annotations

from dataclasses import dataclass

# Retrieval strategy (§7.2 QueryPlan) → ROUTE branch graph-node name.
# Многие стратегии сходятся на одну ветвь → результат де-дублируется ниже.
STRATEGY_TO_BRANCH: dict[str, str] = {
    "cypher_template": "structured_retrieval",
    "graph_algo": "structured_retrieval",
    "hybrid_chunks": "hybrid_retrieval",
    "evidence_lookup": "hybrid_retrieval",
    "graphrag_community": "graphrag_search",
    "gap_scan": "gap_analyzer",
}

# Fallback branch when the plan is empty or every strategy is unknown (§7.2).
DEFAULT_BRANCH: str = "hybrid_retrieval"


def route_after_plan(retrieval_strategy: list[str]) -> list[str]:
    """Map a QueryPlan's ``retrieval_strategy`` onto ordered unique branch nodes.

    Each known strategy is translated via :data:`STRATEGY_TO_BRANCH`; unknown
    strategies are skipped. Duplicate branches (e.g. ``cypher_template`` +
    ``graph_algo`` both → ``structured_retrieval``) are collapsed, keeping the
    first-seen order. An empty or all-unknown input falls back to
    ``[DEFAULT_BRANCH]`` so ROUTE always returns ≥1 branch (§7.2).

    Каждая известная стратегия → ветвь; неизвестные пропускаются, дубли
    сворачиваются с сохранением порядка; пустой ввод → запасная ветвь.
    """
    branches: list[str] = []
    for strategy in retrieval_strategy:
        branch = STRATEGY_TO_BRANCH.get(strategy)
        if branch is not None and branch not in branches:
            branches.append(branch)
    if not branches:
        return [DEFAULT_BRANCH]
    return branches


@dataclass(frozen=True)
class RoutePlan:
    """A resolved §7.2 ROUTE fan-out: the branch nodes to run and their arity.

    Fields
    ------
    branches
        Ordered, de-duplicated branch graph-node names to execute — never empty
        (упорядоченные уникальные ветви маршрута).
    multi
        ``True`` when ≥2 distinct branches fire, i.e. the plan fans out over
        multiple retrieval strategies (многостратегийный запрос).
    """

    branches: tuple[str, ...]
    multi: bool

    def as_dict(self) -> dict[str, object]:
        """Serialise to ``{branches, multi}`` for agent state / logging (§7.3)."""
        return {
            "branches": list(self.branches),
            "multi": self.multi,
        }


def build_route(strategy: list[str]) -> RoutePlan:
    """Build a frozen :class:`RoutePlan` from a QueryPlan ``strategy`` list (§7.2).

    Resolves branches via :func:`route_after_plan`, then sets
    :attr:`RoutePlan.multi` to ``len(branches) > 1``.

    Строит неизменяемый план маршрута; ``multi`` истинно при ≥2 ветвях.
    """
    branches = route_after_plan(strategy)
    return RoutePlan(branches=tuple(branches), multi=len(branches) > 1)
