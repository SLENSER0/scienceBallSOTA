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
    from agent_service.text_quality import is_clean_text

    cites = answer.citations
    grounded: list[str] = []
    unsupported: list[str] = []
    for c in cites:
        eid = c.evidence.evidence_id
        # A citation grounds only if its node exists AND its evidence text is readable:
        # a present-but-junk span (``(cid:NN)`` OCR artifact) is a real node yet useless
        # provenance, so it counts as unsupported and drags coverage/confidence down.
        text = (c.evidence.text or "") if c.evidence else ""
        junk = bool(text) and not is_clean_text(text)
        if eid and not junk and store.get_node(eid) is not None:
            grounded.append(eid)
        else:
            unsupported.append(c.marker)
    coverage = len(grounded) / len(cites) if cites else 1.0

    # §13.12/§13.16: flag numbers stated in the answer without evidence backing.
    nv = validate_answer(answer.answer_markdown, list(cites))

    notes: list[str] = []
    # L-43/L-49: emit a structured ``violations`` list so verifier_retry can route
    # and run_metrics can tally. Each row carries a stable ``id``, a ``kind`` (mapped
    # to a rank by verifier_severity) and a ``severity`` string; ungrounded/uncited
    # claims use severity "unsupported" (fixable by re-retrieval, counted by metrics).
    violations: list[dict[str, Any]] = []
    if unsupported:
        notes.append(f"{len(unsupported)} citation(s) not grounded in the graph")
        for i, marker in enumerate(unsupported):
            violations.append(
                {
                    "id": f"unsupported_citation_{i}",
                    "kind": "unsupported_claim",
                    "severity": "unsupported",
                    "marker": marker,
                    "message": f"citation {marker} not grounded in the graph",
                }
            )
    if not nv.ok:
        nums = nv.numeric_claims_without_evidence
        notes.append(f"{len(nums)} numeric claim(s) without evidence")
        for i, num in enumerate(nums):
            violations.append(
                {
                    "id": f"numeric_claim_{i}",
                    "kind": "numeric_claim_without_evidence",
                    "severity": "unsupported",
                    "number": num,
                    "message": f"numeric claim «{num}» without evidence",
                }
            )
    return {
        "verified": (not unsupported) and nv.ok,
        "coverage": round(coverage, 4),
        "n_citations": len(cites),
        "n_grounded": len(grounded),
        "unsupported": unsupported,
        "numeric_validation": nv.as_dict(),
        "violations": violations,
        "notes": notes,
    }


def apply_verification(store: KuzuGraphStore, answer: AnswerPayload) -> AnswerPayload:
    """Attach the verifier report + cap confidence when a guardrail fails (§13.16)."""
    report = verify_answer(store, answer)
    answer.verifier_report = report
    if answer.confidence is None:
        return answer
    # M-34: cap only from a real guardrail breach, and only from the source that
    # actually fired. Ungrounded citations limit confidence to the grounded
    # coverage; a *measurable* claim without evidence (после H-5 — never an
    # incidental year/count) limits it to 0.5. When every citation grounds and no
    # measurable claim is uncited, confidence is left untouched.
    cap = 1.0
    if report["unsupported"]:
        cap = min(cap, report["coverage"])
    if not report["numeric_validation"]["ok"]:
        # Fabricated numbers are the most damaging failure mode, so the cap bites
        # harder the more uncited measurements there are (0.40 for one → floor 0.25),
        # instead of a flat 0.5 that sat above the old already-low base and never fired.
        n_bad = len(report["numeric_validation"]["numeric_claims_without_evidence"])
        cap = min(cap, max(0.25, 0.45 - 0.05 * n_bad))
    if cap < 1.0:
        answer.confidence = round(min(answer.confidence, cap), 4)
    return answer
