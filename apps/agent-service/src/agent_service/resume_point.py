"""``resume_point`` — §13.20 checkpointer/resume: derive the next §7.2 node.

After an interrupt or crash, a resumed run must continue at the *correct* next
graph node given the checkpointed progress. This module is a **pure**,
LangGraph-independent derivation: given the set of completed node names it
computes, from the canonical §7.2 node order, the single node that should run
next plus the remaining tail.

Логика возобновления (§13.20): по завершённым узлам вычисляем следующий узел
из канонического порядка §7.2, независимо от LangGraph.

The rule is deliberately robust to messy checkpoints:

* The **highest-index** completed node wins — out-of-order or partially
  duplicated progress logs still resume at the right place (берётся макс.
  индекс среди завершённых).
* Unknown node names (not in :data:`NODE_ORDER`) are **ignored** — a stray or
  future label never advances the cursor (неизвестные узлы игнорируются).
* When the last §7.2 node is done, ``next_node`` is ``None`` and the run is
  :func:`is_complete` (завершено — следующего узла нет).
"""

from __future__ import annotations

from dataclasses import dataclass

# Canonical §7.2 agent graph node order. The resume cursor advances strictly
# along this tuple — канонический порядок узлов графа агента (§7.2).
NODE_ORDER: tuple[str, ...] = (
    "preprocess_question",
    "intent_classifier",
    "entity_resolver",
    "query_planner",
    "structured_retrieval",
    "evidence_assembler",
    "verifier",
    "answer_synthesizer",
    "visualization_payload",
)

# O(1) name → position lookup over NODE_ORDER (имя узла → индекс).
_NODE_INDEX: dict[str, int] = {name: i for i, name in enumerate(NODE_ORDER)}


@dataclass(frozen=True)
class ResumePlan:
    """A resolved §13.20 resume point: what is done and what runs next.

    Fields
    ------
    completed
        The recognised completed §7.2 nodes, in :data:`NODE_ORDER`, up to and
        including the highest-index completed node (завершённые узлы по порядку).
    next_node
        The §7.2 node to run next — the entry immediately after the
        highest-index completed node — or ``None`` when the run is complete
        (следующий узел или ``None``, если всё выполнено).
    remaining
        The tail of :data:`NODE_ORDER` starting at ``next_node`` inclusive;
        empty when complete (оставшиеся узлы, включая следующий).
    """

    completed: tuple[str, ...]
    next_node: str | None
    remaining: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Serialise to ``{completed, next_node, remaining}`` for state / logs (§13.20)."""
        return {
            "completed": list(self.completed),
            "next_node": self.next_node,
            "remaining": list(self.remaining),
        }


def _max_completed_index(completed_nodes: list[str]) -> int:
    """Highest :data:`NODE_ORDER` index among ``completed_nodes``, or ``-1``.

    Unknown names are ignored; ``-1`` means nothing recognised is done yet
    (макс. индекс завершённого узла, либо -1).
    """
    max_index = -1
    for name in completed_nodes:
        index = _NODE_INDEX.get(name)
        if index is not None and index > max_index:
            max_index = index
    return max_index


def resume_point(completed_nodes: list[str]) -> ResumePlan:
    """Derive the §13.20 :class:`ResumePlan` from checkpointed completed nodes.

    ``next_node`` is the :data:`NODE_ORDER` entry immediately after the
    highest-index completed node; unknown names are ignored and out-of-order
    input uses the max index seen. ``remaining`` is the tail from ``next_node``
    inclusive. When every §7.2 node is done, ``next_node`` is ``None`` and
    ``remaining`` is empty.

    По завершённым узлам вычисляет следующий узел и хвост §7.2 (§13.20).
    """
    max_index = _max_completed_index(completed_nodes)
    completed = NODE_ORDER[: max_index + 1]
    next_index = max_index + 1
    if next_index >= len(NODE_ORDER):
        return ResumePlan(completed=completed, next_node=None, remaining=())
    return ResumePlan(
        completed=completed,
        next_node=NODE_ORDER[next_index],
        remaining=NODE_ORDER[next_index:],
    )


def is_complete(completed_nodes: list[str]) -> bool:
    """``True`` iff the last §7.2 node (:data:`NODE_ORDER` tail) is completed.

    Истинно тогда и только тогда, когда завершён последний узел §7.2.
    """
    return _max_completed_index(completed_nodes) == len(NODE_ORDER) - 1
