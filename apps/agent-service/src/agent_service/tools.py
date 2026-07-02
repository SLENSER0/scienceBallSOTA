"""Explicit agent tools + a deterministic query planner (§13.6-§13.10).

The LangGraph agent (``agent_service.agent``) runs an implicit parse→retrieve→
synthesize pipeline. This module exposes the same retrieval capabilities as a set
of small, explicit, tool-calling-friendly callables — the tool layer of §13.6 (a
focused, dependency-light subset of the full §7.4 registry) plus the deterministic
``query_planner`` of §13.10.

Each tool is a plain object with ``name``, ``description`` and ``run(store, args)``:

    tool_graph_search      — find candidate solutions/methods/materials (§13.6, §7.5 N5)
    tool_numeric_filter    — filter Measurements by parsed numeric constraints (§13.6)
    tool_evidence_lookup   — gather EvidenceRef-shaped provenance for node ids (§13.6)
    tool_gap_check         — surface Gap / Contradiction nodes (§13.6, §11.1)
    tool_compare_practice  — group solutions by russia/foreign practice (§13.6, §24.13)

``plan_query(intent)`` is pure and deterministic: it inspects a parsed
``QueryIntent`` and returns the ordered list of tool names to run (Mode A/B/D of
§10.1 in miniature) — numeric constraints add ``numeric_filter``, comparison /
geography add ``compare_practice``, a gap query adds ``gap_check`` — always
bracketed by ``graph_search`` first and ``evidence_lookup`` last (evidence-first,
§8.3). ``args_from_intent`` / ``run_plan`` wire an intent through the plan so the
whole thing stays side-effect free and testable on the seed graph.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from kg_extractors.query_parser import QueryIntent
from kg_retrievers.graph_store import KuzuGraphStore

# Node labels that count as a retrievable "solution" vs. any queryable candidate.
SOLUTION_LABELS: tuple[str, ...] = ("TechnologySolution", "Method", "ProcessingRegime")
CANDIDATE_LABELS: tuple[str, ...] = (*SOLUTION_LABELS, "Material", "Equipment")
EVIDENCE_LABELS: tuple[str, ...] = ("Evidence", "Paper")

# Tool names (stable identifiers used by ``plan_query`` and the registry).
GRAPH_SEARCH = "graph_search"
NUMERIC_FILTER = "numeric_filter"
EVIDENCE_LOOKUP = "evidence_lookup"
GAP_CHECK = "gap_check"
COMPARE_PRACTICE = "compare_practice"

_MIN_TERM_LEN = 4  # shorter surface forms (Ni, TDS, RO) are too noisy for CONTAINS


@dataclass(frozen=True)
class Tool:
    """A minimal, LLM-tool-calling-shaped callable over the graph store.

    ``run`` is pure with respect to the store (read-only Cypher) and returns a
    JSON-serialisable ``dict`` — the input/output contract unit-tested in §13.6.
    """

    name: str
    description: str
    run: Callable[[KuzuGraphStore, dict[str, Any]], dict[str, Any]]


# ---------------------------------------------------------------------------
# Small shared helpers (read-only; deterministic ordering)
# ---------------------------------------------------------------------------
def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _terms(args: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for t in _as_list(args.get("terms")):
        s = str(t).strip().lower()
        if len(s) >= _MIN_TERM_LEN and s not in out:
            out.append(s)
    return out


def _collect_nodes(
    store: KuzuGraphStore,
    *,
    ids: list[str],
    domains: list[str],
    terms: list[str],
    labels: tuple[str, ...],
    limit: int,
) -> list[dict[str, Any]]:
    """Find candidate nodes by exact id, domain scope, then alias/name CONTAINS.

    Mirrors the discovery order of ``GraphRetriever._candidates`` (exact → domain →
    surface term) so the tool ranks evidence-rich domain nodes ahead of fuzzy hits,
    while staying self-contained (no coupling to the retriever internals).
    """
    found: dict[str, dict[str, Any]] = {}

    if ids:
        for r in store.rows("MATCH (n:Node) WHERE n.id IN $ids RETURN n", {"ids": ids}):
            nd = store._node_dict(r[0])
            found.setdefault(nd["id"], nd)

    if domains:
        for r in store.rows(
            "MATCH (n:Node) WHERE n.label IN $labels AND n.domain IN $domains RETURN n",
            {"labels": list(labels), "domains": domains},
        ):
            nd = store._node_dict(r[0])
            found.setdefault(nd["id"], nd)

    for term in terms:
        for r in store.rows(
            "MATCH (n:Node) WHERE n.label IN $labels AND "
            "(lower(n.aliases_text) CONTAINS $t OR lower(n.canonical_name) CONTAINS $t "
            "OR lower(n.name) CONTAINS $t) RETURN n LIMIT 25",
            {"labels": list(labels), "t": term},
        ):
            nd = store._node_dict(r[0])
            found.setdefault(nd["id"], nd)

    return list(found.values())[: max(1, limit)]


def _cget(constraint: Any, key: str) -> Any:
    """Read a field off a ``ParsedConstraint`` dataclass or its ``as_dict`` form."""
    if isinstance(constraint, dict):
        return constraint.get(key)
    return getattr(constraint, key, None)


def _passes_numeric(node: dict[str, Any], constraints: list[Any]) -> bool:
    """True if a measurement is *addressed by* and *satisfies* the constraints.

    A constraint only targets a measurement of the same normalized unit (never
    compare bare numbers across dimensions — cf. graph_retriever adversarial
    finding). A measurement is returned only when at least one constraint targets
    it and every targeting constraint passes.
    """
    val = node.get("value_normalized")
    if val is None:
        return False
    node_unit = node.get("normalized_unit")
    applied = 0
    for c in constraints:
        nv = _cget(c, "normalized_value")
        nmin = _cget(c, "normalized_min")
        nmax = _cget(c, "normalized_max")
        if nv is None and nmin is None:
            continue  # nothing comparable (unit unknown / un-normalised)
        cu = _cget(c, "normalized_unit")
        if cu and node_unit != cu:
            continue  # constraint is for a different quantity
        applied += 1
        op = _cget(c, "operator")
        if op == "<=" and nv is not None and val > nv:
            return False
        if op == "<" and nv is not None and val >= nv:
            return False
        if op == ">=" and nv is not None and val < nv:
            return False
        if op == ">" and nv is not None and val <= nv:
            return False
        if op == "=" and nv is not None and val != nv:
            return False
        if (
            op == "range"
            and nmin is not None
            and not (nmin <= val <= (nmax if nmax is not None else nmin))
        ):
            return False
    return applied > 0


def _slim(node: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: node[k] for k in keys if node.get(k) is not None}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def _graph_search(store: KuzuGraphStore, args: dict[str, Any]) -> dict[str, Any]:
    """Return candidate nodes matching ids / domains / surface terms."""
    labels = tuple(_as_list(args.get("labels"))) or CANDIDATE_LABELS
    limit = int(args.get("limit") or 25)
    nodes = _collect_nodes(
        store,
        ids=[str(i) for i in _as_list(args.get("ids"))],
        domains=[str(d) for d in _as_list(args.get("domains"))],
        terms=_terms(args),
        labels=labels,
        limit=limit,
    )
    slim = [
        _slim(n, ("id", "label", "name", "canonical_name", "domain", "practice_type", "operation"))
        for n in nodes
    ]
    return {"nodes": slim, "matched_ids": [n["id"] for n in nodes], "count": len(nodes)}


def _numeric_filter(store: KuzuGraphStore, args: dict[str, Any]) -> dict[str, Any]:
    """Return Measurement nodes satisfying the parsed numeric constraints."""
    constraints = _as_list(args.get("constraints"))
    domains = [str(d) for d in _as_list(args.get("domains"))]
    if domains:
        rows = store.rows(
            "MATCH (n:Node) WHERE n.label='Measurement' AND n.domain IN $domains RETURN n",
            {"domains": domains},
        )
    else:
        rows = store.rows("MATCH (n:Node) WHERE n.label='Measurement' RETURN n")

    keys = ("id", "name", "property_name", "value_normalized", "normalized_unit", "domain")
    measurements: list[dict[str, Any]] = []
    for r in rows:
        nd = store._node_dict(r[0])
        if not constraints or _passes_numeric(nd, constraints):
            measurements.append(_slim(nd, keys))
    measurements.sort(
        key=lambda m: (m.get("property_name") or "", m.get("value_normalized") or 0.0)
    )
    return {
        "measurements": measurements,
        "count": len(measurements),
        "constraints_applied": len(constraints),
    }


def _evidence_lookup(store: KuzuGraphStore, args: dict[str, Any]) -> dict[str, Any]:
    """Assemble EvidenceRef-shaped provenance for node ids and/or evidence ids."""
    node_ids = [str(i) for i in _as_list(args.get("ids"))]
    direct_ev = [str(i) for i in _as_list(args.get("evidence_ids"))]
    refs: dict[str, dict[str, Any]] = {}

    def _add(ev: dict[str, Any], source_id: str) -> None:
        eid = ev.get("id")
        if not eid or eid in refs:
            return
        refs[eid] = {
            "evidence_id": eid,
            "source_id": source_id,
            "doc_id": ev.get("doc_id"),
            "page": ev.get("page"),
            "text": ev.get("text") or ev.get("name"),
            "evidence_strength": ev.get("evidence_strength"),
            "confidence": ev.get("confidence"),
        }

    for nid in node_ids:
        for r in store.rows(
            "MATCH (n:Node {id:$id})-[:Rel]-(ev:Node) WHERE ev.label IN $labels RETURN ev",
            {"id": nid, "labels": list(EVIDENCE_LABELS)},
        ):
            _add(store._node_dict(r[0]), nid)
        for r in store.rows(
            "MATCH (n:Node {id:$id})-[e:Rel]-(:Node) WHERE e.evidence_ids IS NOT NULL "
            "RETURN e.evidence_ids",
            {"id": nid},
        ):
            try:
                eids = json.loads(r[0])
            except (json.JSONDecodeError, TypeError):
                continue
            for eid in eids:
                nd = store.get_node(eid)
                if nd:
                    _add(nd, nid)

    for eid in direct_ev:
        nd = store.get_node(eid)
        if nd:
            _add(nd, eid)

    evidence = sorted(refs.values(), key=lambda e: e.get("confidence") or 0.0, reverse=True)
    return {"evidence": evidence, "count": len(evidence)}


def _gap_check(store: KuzuGraphStore, args: dict[str, Any]) -> dict[str, Any]:
    """Surface Gap and Contradiction nodes for the intent's domains / entities."""
    domains = [str(d) for d in _as_list(args.get("domains"))]
    node_ids = [str(i) for i in _as_list(args.get("ids"))]

    def _find(label: str) -> list[dict[str, Any]]:
        acc: dict[str, dict[str, Any]] = {}
        if domains:
            for r in store.rows(
                "MATCH (n:Node) WHERE n.label=$label AND n.domain IN $domains RETURN n",
                {"label": label, "domains": domains},
            ):
                nd = store._node_dict(r[0])
                acc[nd["id"]] = nd
        if node_ids:
            for r in store.rows(
                "MATCH (n:Node)-[:Rel]-(g:Node {label:$label}) WHERE n.id IN $ids RETURN g",
                {"label": label, "ids": node_ids},
            ):
                nd = store._node_dict(r[0])
                acc[nd["id"]] = nd
        if not domains and not node_ids:  # unscoped: report everything known
            for r in store.rows("MATCH (n:Node {label:$label}) RETURN n", {"label": label}):
                nd = store._node_dict(r[0])
                acc[nd["id"]] = nd
        keys = ("id", "name", "gap_type", "domain", "review_status")
        return [_slim(n, keys) for n in acc.values()]

    gaps = _find("Gap")
    contradictions = _find("Contradiction")
    return {
        "gaps": gaps,
        "contradictions": contradictions,
        "count": len(gaps) + len(contradictions),
    }


def _compare_practice(store: KuzuGraphStore, args: dict[str, Any]) -> dict[str, Any]:
    """Group matching solutions by russia/foreign practice type (§24.13)."""
    nodes = _collect_nodes(
        store,
        ids=[str(i) for i in _as_list(args.get("ids"))],
        domains=[str(d) for d in _as_list(args.get("domains"))],
        terms=_terms(args),
        labels=SOLUTION_LABELS,
        limit=int(args.get("limit") or 25),
    )
    groups: dict[str, list[dict[str, Any]]] = {}
    for n in nodes:
        if n.get("label") not in SOLUTION_LABELS:
            continue
        pt = n.get("practice_type") or "unknown"
        groups.setdefault(pt, []).append(
            _slim(n, ("id", "name", "practice_type", "country", "operation", "domain"))
        )
    total = sum(len(v) for v in groups.values())
    return {
        "groups": groups,
        "practice_types": sorted(groups),
        "count": total,
    }


# ---------------------------------------------------------------------------
# Tool objects + registry
# ---------------------------------------------------------------------------
tool_graph_search = Tool(
    name=GRAPH_SEARCH,
    description=(
        "Find candidate technology solutions, methods, materials or equipment by "
        "taxonomy id, domain scope or alias/name match. Returns matched nodes."
    ),
    run=_graph_search,
)
tool_numeric_filter = Tool(
    name=NUMERIC_FILTER,
    description=(
        "Filter Measurement nodes by parsed numeric constraints (ranges / "
        "inequalities), comparing only within matching normalized units."
    ),
    run=_numeric_filter,
)
tool_evidence_lookup = Tool(
    name=EVIDENCE_LOOKUP,
    description=(
        "Gather evidence-first provenance (EvidenceRef shape: doc_id, page, text) "
        "for the given node ids and/or explicit evidence ids."
    ),
    run=_evidence_lookup,
)
tool_gap_check = Tool(
    name=GAP_CHECK,
    description=(
        "Surface knowledge Gap and Contradiction nodes relevant to the query's "
        "domains or entities (§11.1)."
    ),
    run=_gap_check,
)
tool_compare_practice = Tool(
    name=COMPARE_PRACTICE,
    description=(
        "Group the matching solutions by practice type (russia / foreign / global) "
        "to build a domestic-vs-foreign comparison (§24.13)."
    ),
    run=_compare_practice,
)

TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        tool_graph_search,
        tool_numeric_filter,
        tool_evidence_lookup,
        tool_gap_check,
        tool_compare_practice,
    )
}


# ---------------------------------------------------------------------------
# Deterministic query planner (§13.10)
# ---------------------------------------------------------------------------
def plan_query(intent: QueryIntent) -> list[str]:
    """Pick the ordered tools to run for a parsed intent — pure & deterministic.

    Base retrieval (``graph_search``) always runs first and evidence assembly
    (``evidence_lookup``) always runs last (evidence-first, §8.3). Between them we
    add specialised tools keyed off the intent, in a stable order:

    * numeric constraints present            → ``numeric_filter`` (Mode A, §10.1)
    * comparison / two practices / geography → ``compare_practice`` (§24.13)
    * gap query                              → ``gap_check`` (§11.1)
    """
    plan: list[str] = [GRAPH_SEARCH]
    if intent.numeric_constraints:
        plan.append(NUMERIC_FILTER)
    if (
        intent.is_comparison
        or len(intent.practice_types) >= 2
        or bool(intent.countries)
        or intent.query_type == "comparison"
    ):
        plan.append(COMPARE_PRACTICE)
    if intent.is_gap_query or intent.query_type == "gap":
        plan.append(GAP_CHECK)
    plan.append(EVIDENCE_LOOKUP)
    # de-dupe while preserving order (defensive: branches are mutually distinct)
    seen: set[str] = set()
    return [t for t in plan if not (t in seen or seen.add(t))]


def args_from_intent(intent: QueryIntent) -> dict[str, Any]:
    """Build a generic tool-args dict from a parsed intent (used by ``run_plan``)."""
    terms: list[str] = []
    for e in intent.entities:
        for surface in (e.canonical_ru, e.canonical_en, *e.aliases):
            if surface and len(surface) >= _MIN_TERM_LEN:
                low = surface.lower()
                if low not in terms:
                    terms.append(low)
    return {
        "ids": intent.entity_ids(),
        "domains": intent.domains,
        "terms": terms,
        "constraints": intent.numeric_constraints,
        "practice_types": intent.practice_types,
        "countries": intent.countries,
    }


def run_plan(store: KuzuGraphStore, intent: QueryIntent) -> dict[str, dict[str, Any]]:
    """Execute the planned tools for an intent, returning ``{tool_name: result}``.

    Evidence lookup is fed the ids discovered by graph search so provenance follows
    the retrieved nodes rather than only the taxonomy entities.
    """
    args = args_from_intent(intent)
    results: dict[str, dict[str, Any]] = {}
    for name in plan_query(intent):
        call_args = dict(args)
        if name == EVIDENCE_LOOKUP:
            discovered = results.get(GRAPH_SEARCH, {}).get("matched_ids") or []
            call_args["ids"] = list({*args["ids"], *discovered})
        results[name] = TOOLS[name].run(store, call_args)
    return results
