"""§13.22 стриминг прогресса (SSE) / streaming progress — percent indicator.

Where :mod:`agent_service.node_timeline` opens the box on *per-node timing*
(how long each §7.5 node ran), this module answers a coarser, UI-facing
question: **how far along is the run?** (§13.22). It turns the *set* of §7.5
nodes that have completed into a single progress indicator — a percent plus the
name of the node currently in flight — suitable for pushing over SSE to a
progress bar.

The twelve §7.5 nodes have a fixed canonical order (:data:`CANONICAL_NODES`).
Given the list of completed node names, :func:`compute_progress` counts the
*distinct canonical* ones done (unknown names ignored, duplicates counted once),
derives ``percent = round(completed / total * 100)`` and points ``current`` at
the first canonical node not yet completed (``None`` once all twelve are done).
Every number is hand-checkable, so the tests stay fully deterministic.

* :data:`CANONICAL_NODES` — the 12 §7.5 nodes in canonical order.
* :class:`Progress` — frozen completed/total/percent/current snapshot.
* :func:`compute_progress` — fold a completed-node list into a :class:`Progress`.
"""

from __future__ import annotations

from dataclasses import dataclass

# The 12 §7.5 pipeline nodes in canonical execution order / канонический порядок.
CANONICAL_NODES: tuple[str, ...] = (
    "preprocess_question",
    "intent_classifier",
    "entity_resolver",
    "query_planner",
    "structured_retrieval",
    "hybrid_retrieval",
    "graphrag_search",
    "gap_analyzer",
    "evidence_assembler",
    "verifier",
    "answer_synthesizer",
    "visualization_payload",
)


@dataclass(frozen=True)
class Progress:
    """UI progress snapshot of one run (§13.22) / снимок прогресса прогона.

    ``completed`` is the count of distinct canonical §7.5 nodes finished,
    ``total`` the number of canonical nodes, ``percent`` the rounded
    ``completed / total`` share and ``current`` the next canonical node still
    pending (``None`` when the run is complete / когда всё готово).
    """

    completed: int
    total: int
    percent: int
    current: str | None

    def as_dict(self) -> dict[str, object]:
        """Serialise to ``{'completed','total','percent','current'}`` (1:1 / без потерь)."""
        return {
            "completed": self.completed,
            "total": self.total,
            "percent": self.percent,
            "current": self.current,
        }


def compute_progress(completed_nodes: list[str]) -> Progress:
    """Fold a completed-node list into a :class:`Progress` (§13.22).

    ``completed_nodes`` is the set of §7.5 node names reported done (order and
    duplicates irrelevant). ``total`` is ``len(CANONICAL_NODES)``; ``completed``
    counts the **distinct canonical** names present (non-canonical names are
    ignored / незнакомые узлы игнорируются, дубликаты считаются один раз);
    ``percent`` is ``round(completed / total * 100)``. ``current`` is the first
    canonical node absent from ``completed_nodes`` in canonical order, or
    ``None`` when every canonical node is done (весь конвейер завершён).
    """
    done = set(completed_nodes)
    total = len(CANONICAL_NODES)
    completed = sum(1 for node in CANONICAL_NODES if node in done)
    percent = round(completed / total * 100)

    current: str | None = None
    for node in CANONICAL_NODES:
        if node not in done:
            current = node
            break

    return Progress(completed=completed, total=total, percent=percent, current=current)
