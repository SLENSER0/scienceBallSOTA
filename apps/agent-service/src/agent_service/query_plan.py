"""§13.10 структурный QueryPlan узла 4 (§7.5) / Node-4 structured query plan.

Distinct from :class:`agent_service.tool_planner.ToolPlan` (which plans a *tool
sequence* off a named §7.5 intent): this module models the **§7.5 Node 4 structured
plan JSON** — the LLM planner's declarative description of *what* to retrieve, not
*which tools* to run. It captures the parsed intent, the resolved entities, the
numeric constraints, the ordered retrieval strategies and the expected outputs
(структурный план запроса).

The plan is a frozen, JSON-serialisable :class:`QueryPlan` validated at construction
against two allow-lists:

* :data:`STRATEGY_ALLOWLIST` — the retrieval strategies Node 4 may request
  (``cypher_template``, ``hybrid_chunks``, ``evidence_lookup``, ``gap_scan``,
  ``graphrag_community``, ``graph_algo``); and
* :data:`OUTPUT_ALLOWLIST` — the answer artefacts Node 4 may promise
  (``summary``, ``experiments_table``, ``graph``, ``gaps``).

Any strategy or output outside its allow-list raises ``ValueError`` in
``__post_init__`` — план не может назначить неизвестную стратегию.

:func:`expand_plan` implements **expand-on-retry** (§7.5 verifier loop): when the
verifier report suggests extra strategies, it returns a *new* plan whose
``retrieval_strategy`` is the original followed by the suggested strategies,
de-duplicated and order-preserving (дозаполнение стратегий при повторе). Nothing
here touches the graph store or an LLM, so the whole module is unit-testable offline.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

# Retrieval strategies Node 4 may request (§7.5) — стратегии извлечения.
STRATEGY_ALLOWLIST: frozenset[str] = frozenset(
    {
        "cypher_template",  # Mode A structured Cypher template
        "hybrid_chunks",  # Mode A/B hybrid chunk retrieval (RRF)
        "evidence_lookup",  # §8.3 evidence / provenance pull
        "gap_scan",  # Mode D gap scan (§11.1)
        "graphrag_community",  # Mode C GraphRAG community / global search
        "graph_algo",  # graph-algorithm strategy (centrality, paths …)
    }
)

# Answer artefacts Node 4 may promise (§7.5) — ожидаемые выходы.
OUTPUT_ALLOWLIST: frozenset[str] = frozenset({"summary", "experiments_table", "graph", "gaps"})


@dataclass(frozen=True)
class QueryPlan:
    """The §7.5 Node-4 structured plan for one query (§13.10).

    Frozen and JSON-serialisable via :meth:`as_dict`. The plan is validated at
    construction: every :attr:`retrieval_strategy` member must be in
    :data:`STRATEGY_ALLOWLIST` and every :attr:`expected_outputs` member in
    :data:`OUTPUT_ALLOWLIST`, else ``__post_init__`` raises ``ValueError``.

    Fields
    ------
    intent
        The parsed intent identifier the plan serves (интент запроса).
    entities
        Resolved entity mentions, e.g. ``{"material": "Ti-6Al-4V"}`` (сущности).
    numeric_constraints
        Parsed numeric filters, e.g. ``{"temperature_C": (150, 250)}`` (числовые
        ограничения).
    retrieval_strategy
        Ordered retrieval strategies to run — each in :data:`STRATEGY_ALLOWLIST`
        (стратегии извлечения, по порядку).
    expected_outputs
        Answer artefacts the plan promises — each in :data:`OUTPUT_ALLOWLIST`
        (ожидаемые выходы).
    """

    intent: str
    entities: dict[str, object] = field(default_factory=dict)
    numeric_constraints: dict[str, object] = field(default_factory=dict)
    retrieval_strategy: tuple[str, ...] = ()
    expected_outputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject any strategy/output outside its allow-list (§13.10 validation)."""
        bad_strategies = [s for s in self.retrieval_strategy if s not in STRATEGY_ALLOWLIST]
        if bad_strategies:
            allowed = ", ".join(sorted(STRATEGY_ALLOWLIST))
            raise ValueError(f"unknown retrieval strategy {bad_strategies!r}; allowed: {allowed}")
        bad_outputs = [o for o in self.expected_outputs if o not in OUTPUT_ALLOWLIST]
        if bad_outputs:
            allowed = ", ".join(sorted(OUTPUT_ALLOWLIST))
            raise ValueError(f"unknown expected output {bad_outputs!r}; allowed: {allowed}")

    def as_dict(self) -> dict[str, object]:
        """Serialise to a JSON-ready dict (lists, not tuples) for state/logging (§7.3)."""
        return {
            "intent": self.intent,
            "entities": dict(self.entities),
            "numeric_constraints": dict(self.numeric_constraints),
            "retrieval_strategy": list(self.retrieval_strategy),
            "expected_outputs": list(self.expected_outputs),
        }


def _dedupe_preserve_order(strategies: Iterable[str]) -> tuple[str, ...]:
    """Drop duplicates while preserving first-seen order (порядок сохраняется)."""
    seen: set[str] = set()
    out: list[str] = []
    for strategy in strategies:
        if strategy not in seen:
            seen.add(strategy)
            out.append(strategy)
    return tuple(out)


def expand_plan(plan: QueryPlan, verifier_report: Mapping[str, object]) -> QueryPlan:
    """Expand-on-retry: append verifier-suggested strategies to ``plan`` (§7.5).

    Returns a **new** :class:`QueryPlan` identical to ``plan`` except that its
    :attr:`retrieval_strategy` is the original tuple followed by every strategy in
    ``verifier_report['suggest']``, de-duplicated and order-preserving (original
    order first, new strategies appended once). An empty / missing ``suggest``
    leaves the strategies unchanged. Suggested strategies are still validated
    against :data:`STRATEGY_ALLOWLIST` by the new plan's ``__post_init__``.
    """
    suggested = verifier_report.get("suggest", ())
    if isinstance(suggested, str):  # a lone strategy name, not a sequence
        suggested = (suggested,)
    merged = _dedupe_preserve_order((*plan.retrieval_strategy, *suggested))
    return QueryPlan(
        intent=plan.intent,
        entities=dict(plan.entities),
        numeric_constraints=dict(plan.numeric_constraints),
        retrieval_strategy=merged,
        expected_outputs=plan.expected_outputs,
    )
