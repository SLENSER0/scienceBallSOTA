"""§13.16 verifier guardrails: citation grounding + no-number-without-evidence."""

from __future__ import annotations

from agent_service.verifier import apply_verification, verify_answer

from kg_common import AnswerPayload


class _FakeStore:
    """Minimal graph-store stand-in: only the ids in ``known`` resolve."""

    def __init__(self, known: list[str]) -> None:
        self._known = set(known)

    def get_node(self, node_id: str):  # type: ignore[no-untyped-def]
        return {"id": node_id} if node_id in self._known else None


def _payload(md: str, *, conf: float = 0.8) -> AnswerPayload:
    return AnswerPayload(
        answer_markdown=md,
        citations=[],
        gaps=[],
        contradictions=[],
        used_models=[],
        confidence=conf,
    )


def test_numeric_claim_without_evidence_is_flagged() -> None:
    report = verify_answer(_FakeStore([]), _payload("Твёрдость 148 HV повышается."))
    nv = report["numeric_validation"]
    assert nv["ok"] is False
    assert "148" in nv["numeric_claims_without_evidence"]
    assert report["verified"] is False


def test_answer_without_numbers_verifies() -> None:
    report = verify_answer(_FakeStore([]), _payload("Обратный осмос удаляет сульфаты."))
    assert report["numeric_validation"]["ok"] is True
    assert report["verified"] is True


def test_apply_verification_caps_confidence_on_ungrounded_number() -> None:
    out = apply_verification(_FakeStore([]), _payload("Эффективность 95% достигается.", conf=0.9))
    assert out.verifier_report["numeric_validation"]["ok"] is False
    assert out.confidence is not None and out.confidence <= 0.5
