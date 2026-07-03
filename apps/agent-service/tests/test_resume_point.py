"""Tests for :mod:`agent_service.resume_point` — §13.20 resume-point selector.

Hand-checkable assertions over the canonical §7.2 :data:`NODE_ORDER`: fresh
start, mid-run resume, completion, unknown-node robustness, and out-of-order
checkpoints. Проверки логики возобновления (§13.20).
"""

from __future__ import annotations

from agent_service.resume_point import (
    NODE_ORDER,
    ResumePlan,
    is_complete,
    resume_point,
)


def test_empty_resumes_at_first_node() -> None:
    """(1) No completed nodes → resume at the very first §7.2 node."""
    plan = resume_point([])
    assert plan.next_node == "preprocess_question"
    assert plan.completed == ()
    assert plan.remaining == NODE_ORDER


def test_resume_after_evidence_assembler() -> None:
    """(2) Completed through 'evidence_assembler' → next is 'verifier'."""
    completed = list(NODE_ORDER[: NODE_ORDER.index("evidence_assembler") + 1])
    plan = resume_point(completed)
    assert plan.next_node == "verifier"
    # remaining starts at next_node inclusive.
    assert plan.remaining[0] == "verifier"
    assert plan.remaining == NODE_ORDER[NODE_ORDER.index("verifier") :]


def test_all_nodes_complete() -> None:
    """(3) All nodes done → next_node is None and remaining is empty."""
    plan = resume_point(list(NODE_ORDER))
    assert plan.next_node is None
    assert plan.remaining == ()
    assert plan.completed == NODE_ORDER


def test_is_complete_true_for_full_order() -> None:
    """(4) is_complete over the full NODE_ORDER is True."""
    assert is_complete(list(NODE_ORDER)) is True


def test_is_complete_false_for_partial() -> None:
    """(5) is_complete after only the first node is False."""
    assert is_complete(["preprocess_question"]) is False


def test_unknown_node_ignored() -> None:
    """(6) An unknown node name does not advance the resume cursor."""
    plan = resume_point(["foo"])
    assert plan.next_node == "preprocess_question"
    assert plan.completed == ()
    # An unknown mixed with a real one uses only the real one's index.
    mixed = resume_point(["foo", "preprocess_question", "bar"])
    assert mixed.next_node == "intent_classifier"
    # is_complete also ignores unknowns.
    assert is_complete(["foo", "bar"]) is False


def test_out_of_order_uses_max_index() -> None:
    """(7) Out-of-order input uses the highest index seen ('verifier')."""
    plan = resume_point(["verifier", "preprocess_question"])
    assert plan.next_node == "answer_synthesizer"
    # 'verifier' at index 6 → completed is the whole prefix through it.
    assert plan.completed == NODE_ORDER[: NODE_ORDER.index("verifier") + 1]


def test_as_dict_exposes_fields() -> None:
    """(8) as_dict exposes completed / next_node / remaining."""
    plan = resume_point(["preprocess_question"])
    data = plan.as_dict()
    assert data == {
        "completed": ["preprocess_question"],
        "next_node": "intent_classifier",
        "remaining": list(NODE_ORDER[1:]),
    }


def test_resume_plan_is_frozen() -> None:
    """ResumePlan is an immutable (frozen) dataclass."""
    plan = resume_point([])
    try:
        plan.next_node = "x"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("ResumePlan must be frozen")
    assert isinstance(plan, ResumePlan)
