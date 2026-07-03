"""§13.19 Сборка графа (StateGraph), routing и compile — pure-python topology.

A dependency-free, hand-checkable description of the §7.2 LangGraph agent graph.
No ``langgraph`` import: this module is the *canonical* wiring diagram (the 12
§7.5 nodes plus ``START``/``END`` and every §7.2 edge) that the real compiled
``StateGraph`` must match, plus small helpers to reason about it —
``successors``, ``reachable_from`` (BFS), ``draw_mermaid`` and
``validate_topology``.

Топология / topology (§7.2):

* ``START → preprocess_question → intent_classifier → entity_resolver →
  query_planner``
* ROUTE fan-out ``query_planner →`` {``structured_retrieval``,
  ``hybrid_retrieval``, ``graphrag_search``, ``gap_analyzer``}
* each retrieval branch ``→ evidence_assembler → verifier``
* verifier retry back-edge ``verifier → query_planner`` and forward
  ``verifier → answer_synthesizer → visualization_payload → END``
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

# §7.5 узлы графа / the 12 graph node names, in canonical execution order.
NODE_NAMES: tuple[str, ...] = (
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

# §7.2 ROUTE fan-out: query_planner → эти четыре ветви извлечения / retrieval branches.
RETRIEVAL_BRANCHES: tuple[str, ...] = (
    "structured_retrieval",
    "hybrid_retrieval",
    "graphrag_search",
    "gap_analyzer",
)

START = "START"
END = "END"


@dataclass(frozen=True, slots=True)
class AgentGraph:
    """Неизменяемое описание графа агента / frozen §7.2 agent graph topology."""

    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, list]:
        """JSON-friendly view; edges as ``[a, b]`` pairs (round-trips to tuples)."""
        return {
            "nodes": list(self.nodes),
            "edges": [[a, b] for a, b in self.edges],
        }


def build_agent_graph() -> AgentGraph:
    """Собрать канонический граф §7.2 / build the canonical §7.2 agent graph."""
    nodes: tuple[str, ...] = (START, *NODE_NAMES, END)

    edges: list[tuple[str, str]] = [
        (START, "preprocess_question"),
        ("preprocess_question", "intent_classifier"),
        ("intent_classifier", "entity_resolver"),
        ("entity_resolver", "query_planner"),
    ]
    # ROUTE fan-out (§7.2): query_planner → каждая из четырёх ветвей.
    edges.extend(("query_planner", branch) for branch in RETRIEVAL_BRANCHES)
    # Каждая ветвь → evidence_assembler.
    edges.extend((branch, "evidence_assembler") for branch in RETRIEVAL_BRANCHES)
    edges.append(("evidence_assembler", "verifier"))
    # verifier: retry-обратная дуга к планировщику + прямой путь к синтезу.
    edges.append(("verifier", "query_planner"))
    edges.append(("verifier", "answer_synthesizer"))
    edges.append(("answer_synthesizer", "visualization_payload"))
    edges.append(("visualization_payload", END))

    return AgentGraph(nodes=nodes, edges=tuple(edges))


def successors(g: AgentGraph, node: str) -> tuple[str, ...]:
    """Прямые преемники ``node`` в порядке рёбер / direct successors of ``node``."""
    return tuple(b for a, b in g.edges if a == node)


def reachable_from(g: AgentGraph, start: str) -> frozenset[str]:
    """BFS-достижимость из ``start`` (включая сам узел) / BFS-reachable node set."""
    seen: set[str] = {start}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for nxt in successors(g, current):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return frozenset(seen)


def draw_mermaid(g: AgentGraph) -> str:
    """Mermaid ``flowchart TD`` — одна строка ``A --> B`` на ребро / one line per edge."""
    lines = ["flowchart TD"]
    lines.extend(f"    {a} --> {b}" for a, b in g.edges)
    return "\n".join(lines)


def validate_topology(g: AgentGraph) -> list[str]:
    """Отчёт о проблемах: недостижимые узлы / повисшие концы рёбер / topology issues."""
    problems: list[str] = []
    node_set = set(g.nodes)

    # Повисшие концы рёбер / dangling edge endpoints not in the node set.
    for a, b in g.edges:
        if a not in node_set:
            problems.append(f"dangling edge source: {a!r} not in nodes")
        if b not in node_set:
            problems.append(f"dangling edge target: {b!r} not in nodes")

    # Недостижимые из START узлы (кроме START) / nodes unreachable from START.
    reachable = reachable_from(g, START)
    for node in g.nodes:
        if node != START and node not in reachable:
            problems.append(f"unreachable node: {node!r}")

    return problems
