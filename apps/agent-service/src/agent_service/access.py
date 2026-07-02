"""Role-based access filtering of retrieval results (§24.14 / §19).

External partners never see internal/restricted evidence or expert contact
details; the agent replaces them with a "restricted source exists" note.
"""

from __future__ import annotations

from kg_retrievers.graph_retriever import RetrievalResult
from kg_schema.enums import ConfidentialityLevel, Role

_FULL_ACCESS = {Role.RESEARCHER, Role.ANALYST, Role.PROJECT_MANAGER, Role.ADMIN, Role.CURATOR}
_RESTRICTED_LEVELS = {
    ConfidentialityLevel.INTERNAL,
    ConfidentialityLevel.RESTRICTED,
    ConfidentialityLevel.COMMERCIAL_SECRET,
}


def _is_restricted(node: dict) -> bool:
    lvl = node.get("confidentiality_level")
    return lvl in _RESTRICTED_LEVELS


def apply_access_policy(retrieval: RetrievalResult, role: str) -> RetrievalResult:
    """Mutate+return the retrieval filtered for ``role``. Full-access roles pass."""
    if role in _FULL_ACCESS or role == "admin":
        return retrieval

    redacted = 0
    kept_ev = [ev for ev in retrieval.evidence if not _is_restricted(ev)]
    redacted += len(retrieval.evidence) - len(kept_ev)
    retrieval.evidence = kept_ev

    # drop restricted facts / solutions
    retrieval.facts = [f for f in retrieval.facts if not _is_restricted(f.node)]
    retrieval.solutions = [s for s in retrieval.solutions if not _is_restricted(s)]

    # hybrid passages carry no confidentiality metadata → withhold for restricted
    # roles rather than risk leaking restricted document text (finding agent.py:60).
    if retrieval.passages:
        redacted += len(retrieval.passages)
        retrieval.passages = []

    # graph payload: drop restricted nodes and any edge touching them
    # (finding access.py:41 — graph was built before filtering).
    if retrieval.graph is not None:
        safe_nodes = []
        safe_ids: set[str] = set()
        for n in retrieval.graph.nodes:
            props = n.properties or {}
            if props.get("confidentiality_level") in _RESTRICTED_LEVELS:
                redacted += 1
                continue
            safe_nodes.append(n)
            safe_ids.add(n.id)
        retrieval.graph.nodes = safe_nodes
        retrieval.graph.edges = [
            e for e in retrieval.graph.edges if e.source in safe_ids and e.target in safe_ids
        ]

    if redacted:
        retrieval.evidence.append(
            {
                "id": "restricted:notice",
                "label": "Evidence",
                "name": f"⛔ {redacted} внутренн. источник(ов) скрыто для роли '{role}'",
                "text": "Есть внутренние источники, доступ ограничен.",
                "confidence": 0.0,
                "evidence_strength": "restricted",
            }
        )
    return retrieval
