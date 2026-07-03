"""Admin pipeline/agent DAG view-model for §5.2.8 (React Flow + dagre layout).

Модель представления DAG конвейера/агента для админ-панели (§5.2.8): чистый
построитель, превращающий состояния шагов §9.1 в полезную нагрузку узлов/рёбер
для React Flow (``@xyflow/react``).

The §5.2.8 admin surface renders the §9.1 ingest pipeline as a directed graph in
React Flow. This module is the *pure* builder: it maps a list of per-step state
dicts onto a React Flow ``{nodes, edges}`` payload with a simple left-to-right
layered (dagre-style) layout — the twelve §9.1 stages form a linear chain, so
each stage sits at ``x = stageIndex * DX``, ``y = 0`` with an edge to its
successor.

* :data:`DX`                — default horizontal spacing between stages.
* :class:`PipelineDag`      — frozen ``{nodes, edges}`` React Flow payload.
* :func:`build_pipeline_dag`— assemble the payload from §9.1 step states.

Unknown or missing stages default to status ``pending`` with empty metrics, so
an empty ``step_states`` yields the full twelve-node chain in its initial state.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from api_gateway.pipeline_steps import PIPELINE_STEPS

# Default horizontal spacing (px) between consecutive stages in the layout.
DX: int = 180


@dataclass(frozen=True, slots=True)
class PipelineDag:
    """A React Flow ``{nodes, edges}`` payload for the §5.2.8 pipeline graph.

    Полезная нагрузка React Flow для графа конвейера (§5.2.8): кортежи узлов и
    рёбер. :meth:`as_dict` даёт вид, пригодный для JSON-сериализации.

    Each node is ``{id, position: {x, y}, data: {label, status, metrics}}`` and
    each edge is ``{id, source, target}`` connecting consecutive stages.
    """

    nodes: tuple[dict, ...]
    edges: tuple[dict, ...]

    def as_dict(self) -> dict[str, list[dict]]:
        return {
            "nodes": [dict(n) for n in self.nodes],
            "edges": [dict(e) for e in self.edges],
        }


def build_pipeline_dag(step_states: list[dict], dx: int = DX) -> PipelineDag:
    """Build the §5.2.8 React Flow DAG from §9.1 pipeline ``step_states``.

    Построить DAG React Flow (§5.2.8) из состояний шагов §9.1.

    ``step_states`` carries ``{name, status, metrics}`` dicts; stages absent from
    the list default to status ``pending`` with empty ``metrics``. Nodes follow
    :data:`PIPELINE_STEPS` order, laid out left-to-right at ``x = index * dx``,
    ``y = 0``; edges chain each stage to its successor.
    """

    by_name: dict[str, dict] = {
        s["name"]: s for s in step_states if isinstance(s, dict) and "name" in s
    }

    nodes: list[dict] = []
    for index, name in enumerate(PIPELINE_STEPS):
        state = by_name.get(name, {})
        status = state.get("status", "pending") or "pending"
        metrics = state.get("metrics") or {}
        nodes.append(
            {
                "id": name,
                "position": {"x": index * dx, "y": 0},
                "data": {"label": name, "status": status, "metrics": dict(metrics)},
            }
        )

    edges: list[dict] = []
    for source, target in pairwise(PIPELINE_STEPS):
        edges.append({"id": f"{source}->{target}", "source": source, "target": target})

    return PipelineDag(nodes=tuple(nodes), edges=tuple(edges))
