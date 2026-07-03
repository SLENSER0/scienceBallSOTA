"""openBIS space/project/experiment/sample hierarchy → canonical subgraph (§20.5).

Read-only mapper for the openBIS connector (§20.5): takes a pybis-shaped nested
``space`` dict — as returned by ``pybis`` ``get_spaces()``/``get_samples()`` — and
projects it onto the canonical lab experiment shape of §8.2::

    (:Lab)-[:HAS_PROJECT]->(:Project)-[:HAS_EXPERIMENT]->(:Experiment)
    (:Experiment)-[:USES_SAMPLE]->(:Sample)-[:HAS_MATERIAL]->(:Material)

This module is intentionally pure (no graph-store dependency): it emits plain
``GraphNode``/``GraphEdge`` value objects so the caller (ingest pipeline, §9) can
upsert them, snapshot them for review, or diff them against an existing graph.
Node ids are derived from the openBIS ``permId`` (``openbis:{permId}``), which is
stable across renames, so re-mapping the same space is deterministic (§9.7).
Material nodes are deduped by material name — many samples share one material.

Карта иерархии openBIS (пространство → проект → эксперимент → проба → материал)
в канонический подграф; материалы дедуплицируются по имени.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _oid(perm_id: str) -> str:
    """openBIS permId → canonical node id (``openbis:{permId}``)."""
    return f"openbis:{perm_id}"


@dataclass(frozen=True)
class GraphNode:
    """A canonical graph node: stable ``id``, ``label`` and free-form ``props``."""

    id: str
    label: str
    props: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (``id``, ``label``, ``props``)."""
        return {"id": self.id, "label": self.label, "props": dict(self.props)}


@dataclass(frozen=True)
class GraphEdge:
    """A canonical directed edge: relationship ``type`` from ``from_id`` to ``to_id``."""

    type: str
    from_id: str
    to_id: str

    def as_dict(self) -> dict[str, str]:
        """Serialise to a plain dict (``type``, ``from_id``, ``to_id``)."""
        return {"type": self.type, "from_id": self.from_id, "to_id": self.to_id}


def _name(entity: dict[str, Any], perm_id: str) -> str:
    """Best-effort human name for an openBIS entity, falling back to its permId."""
    for key in ("name", "code", "title"):
        value = entity.get(key)
        if value:
            return str(value)
    return perm_id


def build_subgraph(space: dict[str, Any]) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Map a pybis-shaped openBIS ``space`` into canonical nodes and edges (§20.5).

    The ``space`` dict carries a ``permId`` and nested ``projects`` →
    ``experiments`` → ``samples`` → ``material`` (the last a dict with a ``name``).
    Emits one node per space/project/experiment/sample, one deduped Material node
    per distinct material name, and the ``HAS_PROJECT``/``HAS_EXPERIMENT``/
    ``USES_SAMPLE``/``HAS_MATERIAL`` edges wiring them together.
    """
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    material_ids: dict[str, str] = {}

    space_perm = str(space["permId"])
    lab_id = _oid(space_perm)
    nodes.append(
        GraphNode(lab_id, "Lab", {"name": _name(space, space_perm), "perm_id": space_perm})
    )

    for project in space.get("projects", []) or []:
        proj_perm = str(project["permId"])
        proj_id = _oid(proj_perm)
        nodes.append(
            GraphNode(proj_id, "Project", {"name": _name(project, proj_perm), "perm_id": proj_perm})
        )
        edges.append(GraphEdge("HAS_PROJECT", lab_id, proj_id))

        for experiment in project.get("experiments", []) or []:
            exp_perm = str(experiment["permId"])
            exp_id = _oid(exp_perm)
            nodes.append(
                GraphNode(
                    exp_id,
                    "Experiment",
                    {"name": _name(experiment, exp_perm), "perm_id": exp_perm},
                )
            )
            edges.append(GraphEdge("HAS_EXPERIMENT", proj_id, exp_id))

            for sample in experiment.get("samples", []) or []:
                sample_perm = str(sample["permId"])
                sample_id = _oid(sample_perm)
                nodes.append(
                    GraphNode(
                        sample_id,
                        "Sample",
                        {"name": _name(sample, sample_perm), "perm_id": sample_perm},
                    )
                )
                edges.append(GraphEdge("USES_SAMPLE", exp_id, sample_id))

                material = sample.get("material")
                if not material:
                    continue
                mat_name = str(material["name"])
                mat_id = material_ids.get(mat_name)
                if mat_id is None:
                    mat_id = f"openbis:material:{mat_name}"
                    material_ids[mat_name] = mat_id
                    nodes.append(GraphNode(mat_id, "Material", {"name": mat_name}))
                edges.append(GraphEdge("HAS_MATERIAL", sample_id, mat_id))

    return nodes, edges
