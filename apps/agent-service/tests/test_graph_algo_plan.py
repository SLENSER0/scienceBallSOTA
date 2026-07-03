"""§13.11 тесты планировщика Mode-D / Mode-D graph-algorithm subtask planner tests."""

from __future__ import annotations

import pytest
from agent_service.graph_algo_plan import (
    SUBTASK_ALGO,
    GraphAlgoTask,
    detect_subtask,
    plan_graph_algo,
)


def test_similar_materials_algorithm() -> None:
    """(1) similar_materials → nodeSimilarity."""
    assert plan_graph_algo("similar_materials").algorithm == "nodeSimilarity"


def test_bogus_subtask_raises() -> None:
    """(2) unknown subtask raises ValueError."""
    with pytest.raises(ValueError):
        plan_graph_algo("bogus")


def test_top_k_param() -> None:
    """(3) params['topK'] reflects top_k=5."""
    assert plan_graph_algo("similar_materials", top_k=5).params["topK"] == 5


def test_detect_similar_materials() -> None:
    """(4) natural-language similar-materials query."""
    assert detect_subtask("find materials similar to Al-Cu") == "similar_materials"


def test_detect_none() -> None:
    """(5) non-graph-algorithm query → None."""
    assert detect_subtask("what is hardness") is None


def test_detect_important_labs() -> None:
    """(6) important-labs query."""
    assert detect_subtask("important labs and teams") == "important_labs"


def test_as_dict_exposes_fields() -> None:
    """(7) as_dict exposes subtask, algorithm, params."""
    d = plan_graph_algo("important_labs", top_k=3).as_dict()
    assert d["subtask"] == "important_labs"
    assert d["algorithm"] == "betweennessCentrality"
    assert d["params"] == {"topK": 3}
    assert set(d) == {"subtask", "algorithm", "params"}


def test_method_clusters_maps_to_louvain() -> None:
    """(8) method_clusters → louvain."""
    assert SUBTASK_ALGO["method_clusters"] == "louvain"
    assert plan_graph_algo("method_clusters").algorithm == "louvain"


def test_clustering_has_no_topk() -> None:
    """Louvain/anomaly are not ranking algos → empty params."""
    assert plan_graph_algo("method_clusters").params == {}
    assert plan_graph_algo("anomaly_detection").params == {}


def test_all_subtasks_plannable() -> None:
    """Every SUBTASK_ALGO key builds a consistent GraphAlgoTask."""
    for subtask, algo in SUBTASK_ALGO.items():
        task = plan_graph_algo(subtask)
        assert isinstance(task, GraphAlgoTask)
        assert task.algorithm == algo
        assert task.subtask == subtask


def test_frozen_dataclass() -> None:
    """GraphAlgoTask is immutable."""
    task = plan_graph_algo("similar_materials")
    with pytest.raises((AttributeError, TypeError)):
        task.subtask = "x"  # type: ignore[misc]


def test_detect_missing_links_and_clusters() -> None:
    """Additional keyword coverage for missing_links / method_clusters / anomaly."""
    assert detect_subtask("predict missing links between labs") == "missing_links"
    assert detect_subtask("show clusters of methods") == "method_clusters"
    assert detect_subtask("detect anomaly in the graph") == "anomaly_detection"
