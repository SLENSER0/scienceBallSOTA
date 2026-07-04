"""Structured graph retrieval (§24.9 / §12).

Given a parsed ``QueryIntent`` it finds the relevant technologies/methods/materials
in the graph, gathers their measurements (with numeric filtering), evidence,
applicability, limitations, gaps and contradictions, groups by practice type, and
returns an evidence-first result + a graph payload for the UI.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from kg_common import GraphResponse, get_logger
from kg_extractors.query_parser import QueryIntent
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("graph_retriever")

# The neo4j driver is thread-safe (each store.rows() opens its own session), so
# independent read queries run concurrently instead of one-at-a-time in a Python loop.
_POOL = ThreadPoolExecutor(max_workers=24, thread_name_prefix="retr")

SOLUTION_LABELS = ["TechnologySolution", "Method"]
CANDIDATE_LABELS = [*SOLUTION_LABELS, "ProcessingRegime", "Material", "Equipment"]

# Caps so a dense real corpus doesn't flood an answer with hundreds of items.
MAX_CANDIDATES = 16  # relevance-ordered; top-16 keeps recall while cutting per-cand queries
MAX_FACTS = 40
MAX_SOLUTIONS = 25
MAX_EVIDENCE = 40
MAX_GAPS = 15
MAX_CONTRADICTIONS = 15


@dataclass
class Fact:
    node: dict[str, Any]
    subjects: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"node": self.node, "subjects": self.subjects, "evidence": self.evidence}


@dataclass
class RetrievalResult:
    intent: QueryIntent
    solutions: list[dict[str, Any]] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    grouped_by_practice: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    graph: GraphResponse | None = None
    matched_ids: list[str] = field(default_factory=list)
    passages: list[dict[str, Any]] = field(default_factory=list)  # hybrid fallback (§12)

    def to_dict(self) -> dict[str, Any]:
        return {
            "solutions": self.solutions,
            "facts": [f.to_dict() for f in self.facts],
            "evidence": self.evidence,
            "gaps": self.gaps,
            "contradictions": self.contradictions,
            "grouped_by_practice": self.grouped_by_practice,
            "matched_ids": self.matched_ids,
            "passages": self.passages,
        }


class GraphRetriever:
    def __init__(self, store: KuzuGraphStore) -> None:
        self.store = store

    # -- candidate discovery --------------------------------------------
    def _candidates(self, intent: QueryIntent) -> list[dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}

        # 1) exact taxonomy ids present in the graph
        exact = intent.entity_ids()
        if exact:
            for r in self.store.rows("MATCH (n:Node) WHERE n.id IN $ids RETURN n", {"ids": exact}):
                nd = self.store._node_dict(r[0])
                found[nd["id"]] = nd

        # 2) domain-scoped solutions/methods/regimes
        if intent.domains:
            for r in self.store.rows(
                "MATCH (n:Node) WHERE n.label IN $labels AND n.domain IN $domains RETURN n",
                {"labels": CANDIDATE_LABELS, "domains": intent.domains},
            ):
                nd = self.store._node_dict(r[0])
                found[nd["id"]] = nd

        # 3) alias/name CONTAINS for each entity surface term
        terms: set[str] = set()
        for e in intent.entities:
            for t in (e.canonical_ru, e.canonical_en, *e.aliases):
                if t and len(t) >= 4:
                    terms.add(t.lower())
        def _scan(term: str) -> list[Any]:
            return self.store.rows(
                "MATCH (n:Node) WHERE n.label IN $labels AND "
                "(lower(n.aliases_text) CONTAINS $t OR lower(n.canonical_name) CONTAINS $t "
                "OR lower(n.name) CONTAINS $t) RETURN n LIMIT 25",
                {"labels": CANDIDATE_LABELS, "t": term},
            )

        # Each term is an independent (unindexed) CONTAINS scan — run them concurrently.
        for rows in _POOL.map(_scan, list(terms)):
            for r in rows:
                nd = self.store._node_dict(r[0])
                found[nd["id"]] = nd
        return list(found.values())

    # -- numeric filtering ----------------------------------------------
    @staticmethod
    def _passes_numeric(node: dict[str, Any], intent: QueryIntent) -> bool:
        val = node.get("value_normalized")
        if val is None or not intent.numeric_constraints:
            return True
        for c in intent.numeric_constraints:
            unit = c.normalized_unit
            # A unit-bearing constraint only applies to a measurement of the SAME
            # unit. If the measurement has a different unit OR no unit at all, the
            # constraint is not its target — skip (never compare bare numbers across
            # dimensions). See adversarial finding graph_retriever.py:110.
            if unit and node.get("normalized_unit") != unit:
                continue
            if c.operator == "<=" and c.normalized_value is not None and val > c.normalized_value:
                return False
            if c.operator == "<" and c.normalized_value is not None and val >= c.normalized_value:
                return False
            if c.operator == ">=" and c.normalized_value is not None and val < c.normalized_value:
                return False
            if c.operator == ">" and c.normalized_value is not None and val <= c.normalized_value:
                return False
            if c.operator == "=" and c.normalized_value is not None:
                # Exact-value constraint («концентрация 250 мг/л»). Compare with a
                # small tolerance so float rounding / unit conversion doesn't reject
                # a genuine match; 5% relative, with an absolute floor for val≈0.
                tol = max(abs(c.normalized_value) * 0.05, 1e-9)
                if abs(val - c.normalized_value) > tol:
                    return False
            if c.operator == "range" and c.normalized_min is not None:
                # Use an explicit None check for the upper bound: a legitimate max of
                # 0.0 is falsy and `or` would collapse the range to a point (L-42).
                hi = c.normalized_max if c.normalized_max is not None else c.normalized_min
                if not (c.normalized_min <= val <= hi):
                    return False
        return True

    # -- geographic filtering -------------------------------------------
    @staticmethod
    def _passes_geo(node: dict[str, Any], intent: QueryIntent) -> bool:
        """Keep a fact only if its source geography matches the query (§ гео-фильтр).

        Facts carry ``practice_type`` (russia/cis/foreign/global) and ``country``
        propagated from their source Document. When the query asks for отечественную
        or зарубежную практику (``intent.practice_types``) or a specific country
        (``intent.countries``), drop only facts with a *conflicting* classification.

        Two rules keep the filter from silently gutting the answer:
        * ``practice_type == "global"`` — universally-applicable, peer-reviewed
          facts always pass any geo filter (H-4b).
        * a missing field is NOT a violation. Measurement/Evidence nodes often
          carry no ``country``/``practice_type`` of their own (they inherit geo
          from their source Document); absence must not exclude them (H-4a).
          Only an explicit non-matching value drops a fact.
        """
        if not intent.practice_types and not intent.countries:
            return True
        pt = node.get("practice_type")
        country = node.get("country")
        # Universally-applicable facts (peer-reviewed, geography-agnostic) always pass.
        if pt == "global":
            return True
        if intent.practice_types:
            # "russia" in the query also accepts CIS practice; "foreign" is strict.
            wanted = set(intent.practice_types)
            if "russia" in wanted:
                wanted.add("cis")
            # Exclude only on a conflicting value; a missing practice_type is kept.
            if pt is not None and pt not in wanted:
                return False
        # Exclude only on a conflicting country; a missing country is kept
        # (Measurement/Evidence/Paper may not carry one of their own).
        return not (
            intent.countries and country is not None and country not in intent.countries
        )

    @staticmethod
    def _passes_year(node: dict[str, Any], intent: QueryIntent) -> bool:
        """Keep a fact only if its source publication year is in the query's range."""
        if intent.year_from is None and intent.year_to is None:
            return True
        # Seeded Papers/Measurements may tag the year under either key; check both
        # so provenance-year filtering doesn't silently pass every dated fact (M-37).
        yr = node.get("source_year")
        if yr is None:
            yr = node.get("year")
        if yr is None:
            return True  # undated fact — can't prove it's out of range
        if intent.year_from is not None and yr < intent.year_from:
            return False
        return not (intent.year_to is not None and yr > intent.year_to)

    def _passes_provenance(self, node: dict[str, Any], intent: QueryIntent) -> bool:
        """Combined geo + temporal gate applied to every candidate fact."""
        return self._passes_geo(node, intent) and self._passes_year(node, intent)

    # -- neighborhood assembly ------------------------------------------
    def _neighbors(self, node_id: str) -> list[tuple[dict[str, Any], str]]:
        out = []
        for r in self.store.rows(
            "MATCH (a:Node {id:$id})-[e:Rel]-(b:Node) RETURN b, e.type", {"id": node_id}
        ):
            out.append((self.store._node_dict(r[0]), r[1]))
        return out

    def retrieve(self, intent: QueryIntent) -> RetrievalResult:
        res = RetrievalResult(intent=intent)
        # _candidates already returns in relevance order (exact taxonomy → domain →
        # alias). Keep that order (do NOT re-sort by confidence, which favours
        # generic corpus nodes over evidence-rich ones) and just cap for focus.
        candidates = self._candidates(intent)[:MAX_CANDIDATES]
        res.matched_ids = [c["id"] for c in candidates]

        ev_ids: set[str] = set()
        gap_ids: set[str] = set()
        contra_ids: set[str] = set()
        cutoff_year = None
        if intent.last_n_years:
            cutoff_year = datetime.now(UTC).year - intent.last_n_years

        # Fire every candidate's neighbour + edge-evidence query CONCURRENTLY instead of
        # looping one-at-a-time — the biggest single chunk of retrieval wall-time.
        cand_ids = [c["id"] for c in candidates]
        neigh_map = dict(zip(cand_ids, _POOL.map(self._neighbors, cand_ids), strict=False))
        edge_ev_map = dict(
            zip(cand_ids, _POOL.map(self._edge_evidence_ids, cand_ids), strict=False)
        )

        for cand in candidates:
            label = cand.get("label")
            neigh = neigh_map.get(cand["id"], [])
            if label in SOLUTION_LABELS or label == "ProcessingRegime":
                sol = dict(cand)
                sol["measurements"] = []
                sol["applicability"] = []
                sol["limitations"] = []
                for nb, _rt in neigh:
                    nl = nb.get("label")
                    if (
                        nl == "Measurement"
                        and self._passes_numeric(nb, intent)
                        and self._passes_provenance(nb, intent)
                    ):
                        sol["measurements"].append(nb)
                    elif nl == "ApplicabilityCondition":
                        sol["applicability"].append(nb.get("name"))
                    elif nl == "Limitation":
                        sol["limitations"].append(nb.get("name"))
                    elif nl in ("Evidence", "Paper") and self._passes_provenance(nb, intent):
                        ev_ids.add(nb["id"])
                    elif nl == "Gap":
                        gap_ids.add(nb["id"])
                    elif nl == "Contradiction":
                        contra_ids.add(nb["id"])
                ev_ids.update(edge_ev_map.get(cand["id"], set()))
                res.solutions.append(sol)

            # facts: measurements attached to this candidate
            for nb, _rt in neigh:
                if (
                    nb.get("label") == "Measurement"
                    and self._passes_numeric(nb, intent)
                    and self._passes_provenance(nb, intent)
                ):
                    # Defer evidence: fetch it in ONE batch after facts are capped,
                    # instead of a per-measurement query for facts we then drop.
                    res.facts.append(Fact(node=nb, subjects=[cand], evidence=[]))
                elif nb.get("label") == "Gap":
                    gap_ids.add(nb["id"])
                elif nb.get("label") == "Contradiction":
                    contra_ids.add(nb["id"])
                elif nb.get("label") == "Evidence" and self._passes_provenance(nb, intent):
                    ev_ids.add(nb["id"])

        # time filter on solutions (by connected paper year if present)
        if cutoff_year:
            res.solutions = [
                s for s in res.solutions if (s.get("year") or cutoff_year) >= cutoff_year
            ]

        # keep the most confident facts/solutions so dense corpora stay focused
        res.facts.sort(key=lambda f: f.node.get("confidence") or 0.0, reverse=True)
        res.facts = res.facts[:MAX_FACTS]
        res.solutions = res.solutions[:MAX_SOLUTIONS]

        # Batch-hydrate evidence for ONLY the kept facts (was a per-measurement query
        # inside the loop → hundreds of round-trips for facts we then dropped).
        fact_ev = self._evidence_for_many([f.node["id"] for f in res.facts if f.node.get("id")])
        for f in res.facts:
            f.evidence = fact_ev.get(f.node.get("id"), [])
            ev_ids.update(e["id"] for e in f.evidence if e.get("id"))

        # practice grouping
        for s in res.solutions:
            pt = s.get("practice_type") or "unknown"
            res.grouped_by_practice.setdefault(pt, []).append(s)

        # hydrate evidence / gaps / contradictions (capped)
        res.evidence = self._load_nodes(set(list(ev_ids)[:MAX_EVIDENCE]))
        res.gaps = self._load_nodes(set(list(gap_ids)[:MAX_GAPS]))
        res.contradictions = self._load_nodes(set(list(contra_ids)[:MAX_CONTRADICTIONS]))

        # subgraph payload
        all_ids = set(res.matched_ids) | ev_ids | gap_ids | contra_ids
        res.graph = self.store.subgraph_from_ids(list(all_ids), expand=1)
        _log.info(
            "retrieve.done",
            candidates=len(candidates),
            facts=len(res.facts),
            evidence=len(res.evidence),
            gaps=len(res.gaps),
        )
        return res

    def _evidence_for(self, node_id: str) -> list[dict[str, Any]]:
        rows = self.store.rows(
            "MATCH (n:Node {id:$id})-[:Rel]-(ev:Node) "
            "WHERE ev.label IN ['Evidence', 'Paper'] RETURN ev",
            {"id": node_id},
        )
        out = {r[0]["id"]: self.store._node_dict(r[0]) for r in rows}
        for eid in self._edge_evidence_ids(node_id):
            if eid not in out:
                nd = self.store.get_node(eid)
                if nd:
                    out[eid] = nd
        return list(out.values())

    def _edge_evidence_ids(self, node_id: str) -> set[str]:
        """Evidence ids carried on the edges around a node (edge-level provenance)."""
        import json

        ids: set[str] = set()
        for r in self.store.rows(
            "MATCH (a:Node {id:$id})-[e:Rel]-(:Node) WHERE e.evidence_ids IS NOT NULL "
            "RETURN e.evidence_ids",
            {"id": node_id},
        ):
            try:
                ids.update(json.loads(r[0]))
            except (json.JSONDecodeError, TypeError):
                continue
        return ids

    def _load_nodes(self, ids: set[str]) -> list[dict[str, Any]]:
        # One query instead of get_node() per id (was N+1).
        if not ids:
            return []
        rows = self.store.rows(
            "MATCH (n:Node) WHERE n.id IN $ids RETURN n", {"ids": list(ids)}
        )
        out = [self.store._node_dict(r[0]) for r in rows]
        return [nd for nd in out if nd.get("id")]

    def _evidence_for_many(self, node_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        """Batch evidence for many nodes in ≤3 queries (was _evidence_for per node)."""
        import json as _json

        if not node_ids:
            return {}
        ids = list(dict.fromkeys(node_ids))
        out: dict[str, dict[str, dict[str, Any]]] = {nid: {} for nid in ids}
        # node-level evidence neighbours
        for r in self.store.rows(
            "MATCH (n:Node)-[:Rel]-(ev:Node) WHERE n.id IN $ids "
            "AND ev.label IN ['Evidence', 'Paper'] RETURN n.id, ev",
            {"ids": ids},
        ):
            ev = self.store._node_dict(r[1])
            if ev.get("id"):
                out[r[0]][ev["id"]] = ev
        # edge-level evidence ids (batched), then batch-hydrate those nodes
        edge_ev: dict[str, set[str]] = {}
        for r in self.store.rows(
            "MATCH (a:Node)-[e:Rel]-(:Node) WHERE a.id IN $ids "
            "AND e.evidence_ids IS NOT NULL RETURN a.id, e.evidence_ids",
            {"ids": ids},
        ):
            try:
                edge_ev.setdefault(r[0], set()).update(_json.loads(r[1]))
            except (_json.JSONDecodeError, TypeError):
                continue
        all_eids = {e for s in edge_ev.values() for e in s}
        ev_nodes = {nd["id"]: nd for nd in self._load_nodes(all_eids)}
        for nid, eids in edge_ev.items():
            for eid in eids:
                if eid in ev_nodes:
                    out[nid].setdefault(eid, ev_nodes[eid])
        return {nid: list(d.values()) for nid, d in out.items()}
