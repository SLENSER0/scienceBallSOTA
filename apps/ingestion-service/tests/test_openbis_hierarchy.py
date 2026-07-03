"""openBIS hierarchy → canonical subgraph mapper (§20.5)."""

from __future__ import annotations

from ingestion_service.openbis_hierarchy import GraphEdge, GraphNode, build_subgraph


def _space(*samples: dict) -> dict:
    """A pybis-shaped space with 1 project, 1 experiment and the given samples."""
    return {
        "permId": "SPACE-1",
        "name": "Лаборатория меди",
        "projects": [
            {
                "permId": "PROJ-1",
                "code": "CU_PROJ",
                "experiments": [
                    {
                        "permId": "EXP-1",
                        "code": "CU_EXP",
                        "samples": list(samples),
                    }
                ],
            }
        ],
    }


def test_single_sample_space_maps_to_five_nodes() -> None:
    space = _space({"permId": "SAMP-1", "code": "S1", "material": {"name": "Cu"}})
    nodes, edges = build_subgraph(space)

    assert len(nodes) == 5  # Lab, Project, Experiment, Sample, Material
    labels = {n.label for n in nodes}
    assert labels == {"Lab", "Project", "Experiment", "Sample", "Material"}
    assert "Material" in labels

    types = {e.type for e in edges}
    assert "HAS_PROJECT" in types
    assert "HAS_EXPERIMENT" in types
    assert "USES_SAMPLE" in types
    assert "HAS_MATERIAL" in types

    sample_node = next(n for n in nodes if n.label == "Sample")
    assert sample_node.id == "openbis:" + "SAMP-1"


def test_shared_material_is_deduped_to_one_node() -> None:
    space = _space(
        {"permId": "SAMP-1", "code": "S1", "material": {"name": "Cu"}},
        {"permId": "SAMP-2", "code": "S2", "material": {"name": "Cu"}},
    )
    nodes, edges = build_subgraph(space)

    materials = [n for n in nodes if n.label == "Material"]
    assert len(materials) == 1  # two samples sharing 'Cu' → one Material node
    assert materials[0].props["name"] == "Cu"

    # both samples wired to the single shared material
    has_material = [e for e in edges if e.type == "HAS_MATERIAL"]
    assert len(has_material) == 2
    assert {e.to_id for e in has_material} == {materials[0].id}
    assert {e.from_id for e in has_material} == {"openbis:SAMP-1", "openbis:SAMP-2"}


def test_edges_wire_the_canonical_hierarchy() -> None:
    space = _space({"permId": "SAMP-1", "code": "S1", "material": {"name": "Cu"}})
    _, edges = build_subgraph(space)

    edge_set = {(e.type, e.from_id, e.to_id) for e in edges}
    assert ("HAS_PROJECT", "openbis:SPACE-1", "openbis:PROJ-1") in edge_set
    assert ("HAS_EXPERIMENT", "openbis:PROJ-1", "openbis:EXP-1") in edge_set
    assert ("USES_SAMPLE", "openbis:EXP-1", "openbis:SAMP-1") in edge_set


def test_graph_edge_as_dict_keys() -> None:
    edge = GraphEdge("USES_SAMPLE", "openbis:EXP-1", "openbis:SAMP-1")
    d = edge.as_dict()
    assert set(d.keys()) == {"type", "from_id", "to_id"}
    assert d == {
        "type": "USES_SAMPLE",
        "from_id": "openbis:EXP-1",
        "to_id": "openbis:SAMP-1",
    }


def test_graph_node_as_dict_keys() -> None:
    node = GraphNode("openbis:SAMP-1", "Sample", {"name": "S1"})
    d = node.as_dict()
    assert set(d.keys()) == {"id", "label", "props"}
    assert d["id"] == "openbis:SAMP-1"
    assert d["label"] == "Sample"
    assert d["props"] == {"name": "S1"}


def test_frozen_dataclasses_are_immutable() -> None:
    node = GraphNode("openbis:SAMP-1", "Sample")
    edge = GraphEdge("USES_SAMPLE", "a", "b")
    for obj, attr in ((node, "id"), (edge, "type")):
        try:
            setattr(obj, attr, "mutated")
            raise AssertionError("frozen dataclass should not allow mutation")
        except Exception as exc:  # FrozenInstanceError
            assert exc.__class__.__name__ == "FrozenInstanceError"
