"""Ordered processing-step graph shape (§3.5, §6.5).

Turns the ORDERED list of :class:`~kg_extractors.processing_steps.ProcessingStep`
records produced by ``decompose_processing`` into an explicit ``{nodes, edges}``
graph for the ``ProcessingRegime`` → ``ProcessingStep`` structure. Every step
becomes a node the regime ``HAS_STEP``; consecutive steps are chained with
``NEXT_STEP`` edges in ``step_index`` order («плавка → электроэкстракция», etc.)
so the sequence is queryable independently of the step properties.

Reuse (nothing here is edited): :class:`ProcessingStep` and its ``as_dict`` /
``step_index`` come straight from ``processing_steps`` (§6.5). This module adds
no parsing — it only projects an already-ordered step list into graph form.

Kuzu note: custom step props (temperature_c, atmosphere, …) are NOT queryable
columns; a ``RETURN`` selects the base id columns and the rest are read back via
``get_node()``. Each node here therefore exposes ``node_id`` / ``step_index`` as
the stable base columns, with the full parameter payload under ``props``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kg_extractors.processing_steps import ProcessingStep

# Relationship labels for the ordered processing-regime graph (§3.5).
_HAS_STEP = "HAS_STEP"
_NEXT_STEP = "NEXT_STEP"

# Node id of the synthetic regime root that ``HAS_STEP`` every step.
_REGIME_ID = "regime"


def _step_node_id(step_index: int) -> str:
    """Stable node id for a step at *step_index* («step_0», «step_1», …)."""
    return f"step_{step_index}"


@dataclass(frozen=True)
class GraphNode:
    """One graph node: the regime root or a single :class:`ProcessingStep`.

    ``node_id`` and ``step_index`` are the Kuzu base id columns; the step's full
    parameter payload (operation / temperature / time / …) lives in ``props``.
    The regime root has ``step_index=-1`` and an empty ``props``.
    """

    node_id: str
    label: str
    step_index: int
    props: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "label": self.label,
            "step_index": self.step_index,
            "props": dict(self.props),
        }


@dataclass(frozen=True)
class GraphEdge:
    """A directed edge ``source -> target`` of relationship type ``rel``."""

    source: str
    target: str
    rel: str

    def as_dict(self) -> dict[str, object]:
        return {"source": self.source, "target": self.target, "rel": self.rel}


@dataclass(frozen=True)
class ProcessingGraph:
    """The ``{nodes, edges}`` projection of an ordered processing-step list.

    ``nodes`` starts with the regime root followed by one node per step in
    ``step_index`` order; ``edges`` holds the ``HAS_STEP`` fan-out then the
    ``NEXT_STEP`` chain. An empty step list yields the lone regime root and no
    edges.
    """

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "nodes": [n.as_dict() for n in self.nodes],
            "edges": [e.as_dict() for e in self.edges],
        }


def _regime_node() -> GraphNode:
    return GraphNode(node_id=_REGIME_ID, label="ProcessingRegime", step_index=-1)


def steps_to_graph(steps: list[ProcessingStep]) -> ProcessingGraph:
    """Project ORDERED *steps* into a ``ProcessingRegime`` graph (§3.5, §6.5).

    Builds one ``GraphNode`` per step (label ``ProcessingStep``) plus a single
    ``ProcessingRegime`` root. Adds a ``HAS_STEP`` edge from the root to every
    step and a ``NEXT_STEP`` edge between each consecutive pair, following the
    steps' existing order (their ``step_index`` is preserved on the nodes).
    """
    ordered = sorted(steps, key=lambda s: s.step_index)
    nodes: list[GraphNode] = [_regime_node()]
    edges: list[GraphEdge] = []
    prev_id: str | None = None
    for step in ordered:
        node_id = _step_node_id(step.step_index)
        nodes.append(
            GraphNode(
                node_id=node_id,
                label="ProcessingStep",
                step_index=step.step_index,
                props=step.as_dict(),
            )
        )
        edges.append(GraphEdge(source=_REGIME_ID, target=node_id, rel=_HAS_STEP))
        if prev_id is not None:
            edges.append(GraphEdge(source=prev_id, target=node_id, rel=_NEXT_STEP))
        prev_id = node_id
    return ProcessingGraph(nodes=tuple(nodes), edges=tuple(edges))
