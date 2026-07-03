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
    """Two guardrails (§13.16/§7.5): every citation must ground to a real node, and
    every numeric claim in the prose must carry an inline ``[n]`` citation.
    """
    from agent_service.answer_validator import validate_answer

    cites = answer.citations
    grounded: list[str] = []
    unsupported: list[str] = []
    for c in cites:
        eid = c.evidence.evidence_id
        if eid and store.get_node(eid) is not None:
            grounded.append(eid)
        else:
            unsupported.append(c.marker)
    coverage = len(grounded) / len(cites) if cites else 1.0

    # §13.12/§13.16: flag numbers stated in the answer without evidence backing.
    nv = validate_answer(answer.answer_markdown, list(cites))

    notes: list[str] = []
    if unsupported:
        notes.append(f"{len(unsupported)} citation(s) not grounded in the graph")
    if not nv.ok:
        n = len(nv.numeric_claims_without_evidence)
        notes.append(f"{n} numeric claim(s) without evidence")
    return {
        "verified": (not unsupported) and nv.ok,
        "coverage": round(coverage, 4),
        "n_citations": len(cites),
        "n_grounded": len(grounded),
        "unsupported": unsupported,
        "numeric_validation": nv.as_dict(),
        "notes": notes,
    }


def apply_verification(store: KuzuGraphStore, answer: AnswerPayload) -> AnswerPayload:
    """Attach the verifier report + cap confidence when a guardrail fails (§13.16)."""
    report = verify_answer(store, answer)
    answer.verifier_report = report
    if not report["verified"] and answer.confidence is not None:
        cap = report["coverage"]
        if not report["numeric_validation"]["ok"]:
            # numbers without evidence → confidence cannot read as high/trustworthy
            cap = min(cap, 0.5)
        answer.confidence = round(min(answer.confidence, cap), 4)
    return answer
