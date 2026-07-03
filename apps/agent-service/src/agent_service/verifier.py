"""Answer verifier node (§13.16 / §7.5).

A post-synthesis guardrail: every citation in the answer must resolve to a real
source/evidence node in the graph. Ungrounded citations are flagged and the
answer's confidence is capped, so a plausible-but-unsupported claim can't pass as
verified. Runs as the final LangGraph node after synthesize.
"""

from __future__ import annotations

from typing import Any

from kg_common import AnswerPayload
from kg_retrievers.graph_store import KuzuGraphStore


def verify_answer(store: KuzuGraphStore, answer: AnswerPayload) -> dict[str, Any]:
    """Ground each citation against a real node; return a verifier report."""
    cites = answer.citations
    if not cites:
        return {
            "verified": True,
            "coverage": 1.0,
            "n_citations": 0,
            "unsupported": [],
            "notes": ["answer carries no citations"],
        }
    grounded: list[str] = []
    unsupported: list[str] = []
    for c in cites:
        eid = c.evidence.evidence_id
        if eid and store.get_node(eid) is not None:
            grounded.append(eid)
        else:
            unsupported.append(c.marker)
    coverage = len(grounded) / len(cites)
    notes = []
    if unsupported:
        notes.append(f"{len(unsupported)} citation(s) not grounded in the graph")
    return {
        "verified": not unsupported,
        "coverage": round(coverage, 4),
        "n_citations": len(cites),
        "n_grounded": len(grounded),
        "unsupported": unsupported,
        "notes": notes,
    }


def apply_verification(store: KuzuGraphStore, answer: AnswerPayload) -> AnswerPayload:
    """Attach the verifier report + cap confidence when citations are ungrounded."""
    report = verify_answer(store, answer)
    answer.verifier_report = report
    if not report["verified"] and answer.confidence is not None:
        # ungrounded citations → confidence cannot exceed the grounded coverage
        answer.confidence = round(min(answer.confidence, report["coverage"]), 4)
    return answer
