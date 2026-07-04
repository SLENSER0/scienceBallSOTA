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

    # §23.27 source-trust penalty. The trust engine (kg_retrievers.citation_trust)
    # already fuses retraction / freshness / peer-review into a per-warning
    # multiplicative confidence penalty; here we finally apply it to the LIVE answer.
    # Each citation is enriched with its source node's metadata; the grounding-capped
    # confidence is used as the base so the two guardrails stack. A retracted source
    # that is the primary support bites hardest.
    trust_inputs = _citation_trust_inputs(store, answer.citations)
    if trust_inputs:
        from kg_retrievers.citation_trust import assess_answer

        trust = assess_answer(trust_inputs, base_confidence=float(answer.confidence))
        answer.confidence = round(trust.adjusted_confidence, 4)
        answer.trust_report = trust.as_dict()
    return answer


_PEER_STRENGTHS = frozenset({"peer_reviewed", "peer-reviewed", "peerreviewed"})
_DAYS_PER_YEAR = 365.25


def _citation_trust_inputs(
    store: KuzuGraphStore, citations: Any
) -> list[dict[str, Any]]:
    """Build citation dicts for :func:`citation_trust.assess_answer`, enriched with
    each source node's metadata (source_status / age_days / peer_reviewed /
    citation_count). Mirrors the source-trust router's ``_source_meta_from_store``
    but reads from the agent's own store. The first citation (marker ``[1]``) is the
    primary support, so a retracted primary triggers the full penalty (§23.27)."""
    from datetime import UTC, datetime

    now_year = datetime.now(UTC).year
    out: list[dict[str, Any]] = []
    for i, c in enumerate(citations or []):
        doc_id = getattr(getattr(c, "evidence", None), "doc_id", None)
        if not doc_id:
            continue
        rec: dict[str, Any] = {
            "doc_id": doc_id,
            "primary": i == 0 or getattr(c, "marker", "") == "[1]",
        }
        node = None
        try:
            node = store.get_node(doc_id)
        except Exception:  # pragma: no cover - store defensiveness
            node = None
        year = node.get("year") if node else None
        if not isinstance(year, int) or year <= 0:
            year = getattr(c, "year", None)
        if isinstance(year, int) and year > 0:
            rec["age_days"] = max(0.0, (now_year - year) * _DAYS_PER_YEAR)
        if node:
            status = node.get("source_status")
            if not status and node.get("retracted") is True:
                status = "retracted"
            if status:
                rec["source_status"] = str(status)
            strength = str(node.get("evidence_strength") or "").strip().lower()
            review = str(node.get("review_status") or "").strip().lower()
            if strength in _PEER_STRENGTHS or review == "accepted":
                rec["peer_reviewed"] = True
            cc = node.get("citation_count")
            if isinstance(cc, int):
                rec["citation_count"] = cc
        out.append(rec)
    return out
