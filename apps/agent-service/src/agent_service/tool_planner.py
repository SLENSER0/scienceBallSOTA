"""§13.10 план последовательности инструментов по интенту / query-intent tool planner.

Companion to :mod:`agent_service.intent_taxonomy` (the nine named §7.5 intents) and
to the deterministic ``plan_query`` of :mod:`agent_service.tools` (which plans off a
*parsed* ``QueryIntent``). This module plans one level up: given only the **named
§7.5 intent** (плюс сырой текст запроса), it returns an ordered ``ToolPlan`` — the
tool sequence the §7.5 orchestrator should run for that intent.

Pure python, deterministic, dependency-light: it imports **only** the nine
:class:`~agent_service.intent_taxonomy.Intent` values (reused, never edited) and
maps each to a fixed, evidence-first tool sequence. Nothing here touches the graph
store, the retrievers or an LLM, so the whole module is unit-testable offline.

Design (§13.10, §8.3 evidence-first):

* every retrieval intent ends with an **evidence step** (``evidence_lookup`` /
  ``get_evidence_by_ids``) — доказательства последними;
* entity-centric intents start by resolving mentions (``resolve_entities``);
* ``gap_analysis`` leads with ``gap_check``; ``literature_summary`` leads with
  ``global_search`` (Mode C); ``schema_help`` needs no retrieval (``graph_schema``);
* :attr:`ToolPlan.parallel` is **derived**, not hand-set: it is ``True`` iff the
  plan fans out over ≥2 mutually-independent retrieval strategies
  (:data:`_INDEPENDENT_STRATEGIES`) — e.g. semantic ``hybrid_search`` *and*
  structured ``graph_search`` for ``material_regime_property_query``;
* an unknown / empty intent degrades to :data:`DEFAULT_STEPS` (a safe Mode-A plan);
* the raw ``query`` refines only measurement intents: a number+unit constraint
  («180°C», «250 МПа») inserts ``numeric_filter`` (Mode A numeric, §10.1).

Every emitted step name is a member of :data:`KNOWN_TOOLS` — the union of the §7.4
named-tool registry (16), the focused §13.6 tool layer (6) and the §6.2
``graph_schema`` descriptor used by the no-retrieval intent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent_service.intent_taxonomy import Intent

# --- known tool-name universe ----------------------------------------------
# Mirrored (not imported) from ``agent_service.tools`` / ``tools_ext`` to keep the
# planner import-light and free of retriever/store dependencies. Kept in sync by
# the module invariant asserted at import time (see bottom of file).

# Focused §13.6 tool layer (agent_service.tools).
_FOCUSED_TOOLS: frozenset[str] = frozenset(
    {
        "graph_search",
        "numeric_filter",
        "evidence_lookup",
        "gap_check",
        "compare_practice",
        "global_search",
    }
)

# Canonical §7.4 named-tool registry — exactly the 16 names (agent_service.tools_ext).
_SPEC_7_4_TOOLS: frozenset[str] = frozenset(
    {
        "resolve_entities",
        "search_material_aliases",
        "run_cypher_readonly",
        "run_cypher_template",
        "vector_search_qdrant",
        "keyword_search_opensearch",
        "hybrid_search",
        "get_experiment_table",
        "get_evidence_by_ids",
        "get_document_snippet",
        "find_graph_paths",
        "expand_subgraph",
        "scan_gaps",
        "detect_contradictions",
        "build_graph_visualization_payload",
        "create_review_task",
    }
)

# §6.2 /graph/schema descriptor — served without retrieval (schema_help intent).
_GRAPH_SCHEMA = "graph_schema"

# Every step a plan may emit (§7.4 ∪ §13.6 ∪ graph_schema).
KNOWN_TOOLS: frozenset[str] = _SPEC_7_4_TOOLS | _FOCUSED_TOOLS | {_GRAPH_SCHEMA}

# Evidence steps (§8.3): a retrieval plan must end on one of these.
EVIDENCE_STEPS: frozenset[str] = frozenset({"evidence_lookup", "get_evidence_by_ids"})

# Mutually-independent retrieval strategies. A plan touching ≥2 of these can fan out
# concurrently → :attr:`ToolPlan.parallel` is ``True`` (multi-strategy retrieval).
_INDEPENDENT_STRATEGIES: frozenset[str] = frozenset(
    {
        "graph_search",  # structured / Cypher (Mode A)
        "hybrid_search",  # semantic RRF fusion (Mode A/B)
        "global_search",  # community / GraphRAG global (Mode C)
        "gap_check",  # gap scan (Mode D)
        "detect_contradictions",  # contradiction scan (Mode D)
        "compare_practice",  # practice-split comparison (§24.13)
    }
)

# A number immediately followed by a physical unit (число + единица) — a Mode-A
# measurement constraint that adds ``numeric_filter`` for measurement intents.
_MEASUREMENT_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s?"
    r"(?:°\s?[cсCС]|мпа|гпа|кпа|hv|hrc|hb|вт|квт|нм|мкм|мм|см|%|"
    r"mpa|gpa|kpa|nm|um|mm|cm)",
    re.IGNORECASE,
)

# Measurement intents whose plan gains ``numeric_filter`` on a number+unit query.
_MEASUREMENT_INTENTS: frozenset[Intent] = frozenset(
    {Intent.MATERIAL_REGIME_PROPERTY_QUERY, Intent.EXPERIMENT_LOOKUP}
)


# --- per-intent tool sequences (§13.10) ------------------------------------
# Ordered, evidence-first tool steps for each of the nine §7.5 intents. Tuples keep
# the table immutable; the public plan exposes them as a fresh ``list`` each call.
_PLANS: dict[Intent, tuple[str, ...]] = {
    # Mode A structured «material X + regime Y + property Z»: resolve → fan out over
    # semantic + structured retrieval → evidence.
    Intent.MATERIAL_REGIME_PROPERTY_QUERY: (
        "resolve_entities",
        "hybrid_search",
        "graph_search",
        "evidence_lookup",
    ),
    # Mode B «расскажи о …» / neighbourhood walk (single graph strategy).
    Intent.ENTITY_EXPLORATION: (
        "resolve_entities",
        "expand_subgraph",
        "graph_search",
        "evidence_lookup",
    ),
    # Experiment / опыты lookup — tabular experiments then graph context.
    Intent.EXPERIMENT_LOOKUP: (
        "resolve_entities",
        "get_experiment_table",
        "graph_search",
        "evidence_lookup",
    ),
    # «покажи доказательства» — evidence-first request pulls provenance twice.
    Intent.EVIDENCE_REQUEST: (
        "resolve_entities",
        "graph_search",
        "get_evidence_by_ids",
        "evidence_lookup",
    ),
    # GAP branch (§11.1) — leads with the gap scan, fans out with graph search.
    Intent.GAP_ANALYSIS: (
        "gap_check",
        "graph_search",
        "evidence_lookup",
    ),
    # Contradiction branch (§11.1) — dedicated conflict scan + graph fan-out.
    Intent.CONTRADICTION_ANALYSIS: (
        "resolve_entities",
        "detect_contradictions",
        "graph_search",
        "evidence_lookup",
    ),
    # «X vs Y» — resolve both sides, graph search, then practice/method comparison.
    Intent.METHOD_COMPARISON: (
        "resolve_entities",
        "graph_search",
        "compare_practice",
        "evidence_lookup",
    ),
    # Mode C literature summary — leads with community/global search + semantic.
    Intent.LITERATURE_SUMMARY: (
        "global_search",
        "hybrid_search",
        "evidence_lookup",
    ),
    # Schema help — «какие есть типы узлов» → static schema, no retrieval.
    Intent.SCHEMA_HELP: (_GRAPH_SCHEMA,),
}

# Fallback plan for an unknown / empty intent — a safe Mode-A structured sequence.
DEFAULT_STEPS: tuple[str, ...] = ("resolve_entities", "graph_search", "evidence_lookup")

# intent-name string → :class:`Intent` (accepts the raw value passed by callers).
_NAME_TO_INTENT: dict[str, Intent] = {i.value: i for i in Intent}


def _is_multi_strategy(steps: tuple[str, ...]) -> bool:
    """``True`` iff ``steps`` fan out over ≥2 independent retrieval strategies."""
    return sum(1 for s in steps if s in _INDEPENDENT_STRATEGIES) >= 2


def _coerce_intent(intent: Intent | str | None) -> tuple[str, Intent | None]:
    """Normalise ``intent`` to ``(name, matched_enum_or_None)`` — never raises.

    Accepts an :class:`Intent`, its string value (any case) or ``None``. An
    unrecognised name resolves to ``(name, None)`` so the caller can fall back to
    :data:`DEFAULT_STEPS` (неизвестный интент → план по умолчанию).
    """
    if isinstance(intent, Intent):
        return intent.value, intent
    name = str(intent or "").strip().lower()
    return name, _NAME_TO_INTENT.get(name)


@dataclass(frozen=True)
class ToolPlan:
    """An ordered tool sequence planned for a §7.5 intent (§13.10).

    Fields
    ------
    intent
        The (normalised) intent identifier the plan was built for — one of the nine
        §7.5 :class:`Intent` values, or the raw string / ``""`` for an unknown intent
        (интент запроса).
    steps
        Ordered tool-step names to run, every one a member of :data:`KNOWN_TOOLS`
        (последовательность инструментов). Never empty.
    parallel
        ``True`` when the steps fan out over ≥2 independent retrieval strategies and
        may run concurrently (многостратегийный запрос → параллельно).
    """

    intent: str
    steps: list[str] = field(default_factory=list)
    parallel: bool = False

    def as_dict(self) -> dict[str, object]:
        """Serialise to ``{intent, steps, parallel}`` for agent state / logging (§7.3)."""
        return {
            "intent": self.intent,
            "steps": list(self.steps),
            "parallel": self.parallel,
        }


def plan_tools(intent: Intent | str | None, query: str = "") -> ToolPlan:
    """Plan the ordered tool sequence for a §7.5 ``intent`` — pure & deterministic.

    Maps each of the nine named intents to its fixed, evidence-first step list
    (:data:`_PLANS`); an unknown or empty intent degrades to :data:`DEFAULT_STEPS`.
    The raw ``query`` refines only measurement intents — a number+unit constraint
    («180°C») inserts ``numeric_filter`` before the trailing evidence step (Mode A
    numeric, §10.1). :attr:`ToolPlan.parallel` is derived from the final steps.

    Same ``(intent, query)`` always yields an equal plan; ``query`` may be empty and
    the function never raises. Every emitted step is a member of :data:`KNOWN_TOOLS`.
    """
    name, matched = _coerce_intent(intent)
    steps: list[str] = list(_PLANS.get(matched, DEFAULT_STEPS) if matched else DEFAULT_STEPS)

    # Query refinement: a measurement constraint adds numeric_filter (Mode A, §10.1).
    if (
        matched in _MEASUREMENT_INTENTS
        and "numeric_filter" not in steps
        and _MEASUREMENT_RE.search(query or "")
    ):
        insert_at = len(steps)
        if steps and steps[-1] in EVIDENCE_STEPS:
            insert_at -= 1  # keep evidence last (§8.3)
        steps.insert(insert_at, "numeric_filter")

    return ToolPlan(intent=name, steps=steps, parallel=_is_multi_strategy(tuple(steps)))


# Module invariant: every step of every plan (and the fallback) is a known tool.
assert all(step in KNOWN_TOOLS for steps in _PLANS.values() for step in steps), (
    "every planned step must be a KNOWN_TOOLS member"
)
assert all(step in KNOWN_TOOLS for step in DEFAULT_STEPS), "DEFAULT_STEPS must be known tools"
