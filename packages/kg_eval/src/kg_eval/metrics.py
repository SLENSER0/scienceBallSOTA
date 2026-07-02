"""Scoring an AnswerPayload against a GoldenCase (§24.18)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kg_common import AnswerPayload
from kg_eval.golden import GoldenCase


@dataclass
class CaseResult:
    id: str
    title: str
    checks: dict[str, bool] = field(default_factory=dict)
    entity_recall: float = 0.0
    passed: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        if not self.checks:
            return 0.0
        return sum(self.checks.values()) / len(self.checks)


def score_case(case: GoldenCase, ans: AnswerPayload) -> CaseResult:
    r = CaseResult(id=case.id, title=case.title)
    pq: dict[str, Any] = ans.parsed_query or {}
    ent_ids = {e.get("id") for e in pq.get("entities", [])}

    # entity recall
    if case.expected_entities:
        hit = [e for e in case.expected_entities if e in ent_ids]
        r.entity_recall = len(hit) / len(case.expected_entities)
        r.checks["entities"] = r.entity_recall >= 0.75
        if r.entity_recall < 1.0:
            missing = set(case.expected_entities) - ent_ids
            r.notes.append(f"missing entities: {sorted(missing)}")

    # numeric constraint units
    if case.expected_constraint_units:
        units = {c.get("normalized_unit") for c in pq.get("numeric_constraints", [])}
        r.checks["units"] = all(u in units for u in case.expected_constraint_units)

    # geography / practice type
    if case.expected_practice_types:
        pts = set(pq.get("practice_types", []))
        r.checks["practice"] = set(case.expected_practice_types) <= pts

    if case.expected_last_n_years is not None:
        r.checks["time"] = pq.get("last_n_years") == case.expected_last_n_years

    if case.expected_query_type:
        r.checks["query_type"] = pq.get("query_type") == case.expected_query_type

    if case.expected_comparison:
        r.checks["comparison"] = bool(pq.get("is_comparison"))

    # evidence-first
    r.checks["evidence"] = len(ans.citations) >= case.min_evidence

    if case.expect_gap:
        r.checks["gap"] = len(ans.gaps) > 0
    if case.expect_contradiction:
        r.checks["contradiction"] = len(ans.contradictions) > 0
    if case.expect_table:
        r.checks["table"] = ans.table is not None and len(ans.table.get("rows", [])) > 0

    if case.expect_solutions:
        low = ans.answer_markdown.lower()
        r.checks["solutions"] = all(s.lower() in low for s in case.expect_solutions)

    if case.expect_facts_property:
        # the property should surface somewhere in the answer or graph
        blob = ans.answer_markdown.lower()
        node_types = " ".join(n.type for n in (ans.graph.nodes if ans.graph else []))
        r.checks["facts_property"] = (
            case.expect_facts_property.replace("_", " ") in blob or "Measurement" in node_types
        )

    r.passed = all(r.checks.values()) if r.checks else False
    return r
