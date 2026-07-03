"""§13.22 tests — streaming progress percent from completed §7.5 nodes."""

from __future__ import annotations

from agent_service.stream_progress import CANONICAL_NODES, Progress, compute_progress


def test_empty_yields_zero_and_first_node() -> None:
    """(1) [] → completed 0, percent 0, current 'preprocess_question'."""
    progress = compute_progress([])
    assert progress.completed == 0
    assert progress.percent == 0
    assert progress.current == "preprocess_question"


def test_all_twelve_nodes_complete() -> None:
    """(2) all 12 nodes → percent 100 and current None."""
    progress = compute_progress(list(CANONICAL_NODES))
    assert progress.completed == 12
    assert progress.total == 12
    assert progress.percent == 100
    assert progress.current is None


def test_first_six_nodes_is_half() -> None:
    """(3) the first 6 nodes → percent 50 (6/12)."""
    progress = compute_progress(list(CANONICAL_NODES[:6]))
    assert progress.completed == 6
    assert progress.percent == 50
    assert progress.current == "graphrag_search"


def test_unrecognized_node_ignored() -> None:
    """(4) an unknown node name is not counted."""
    progress = compute_progress(["preprocess_question", "not_a_real_node"])
    assert progress.completed == 1
    assert progress.percent == round(1 / 12 * 100)


def test_duplicated_node_counted_once() -> None:
    """(5) a duplicated completed node is counted a single time."""
    progress = compute_progress(["preprocess_question", "preprocess_question"])
    assert progress.completed == 1
    assert progress.current == "intent_classifier"


def test_current_is_next_uncompleted_in_canonical_order() -> None:
    """(6) current is the next pending node in canonical order, not report order."""
    # entity_resolver reported before intent_classifier; the gap is at index 1.
    progress = compute_progress(["preprocess_question", "entity_resolver"])
    assert progress.completed == 2
    assert progress.current == "intent_classifier"


def test_as_dict_keys() -> None:
    """(7) as_dict exposes completed/total/percent/current."""
    payload = compute_progress(["preprocess_question"]).as_dict()
    assert set(payload) == {"completed", "total", "percent", "current"}
    assert payload["completed"] == 1
    assert payload["total"] == 12
    assert payload["current"] == "intent_classifier"


def test_progress_is_frozen() -> None:
    """Progress is an immutable frozen dataclass (house style)."""
    import dataclasses

    progress = Progress(completed=0, total=12, percent=0, current="preprocess_question")
    try:
        progress.completed = 5  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - guards the frozen contract
        raise AssertionError("Progress must be frozen")
