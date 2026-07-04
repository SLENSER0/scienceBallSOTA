"""M-34 + L-43/L-49 regression for the verifier ⇆ retry/metrics contract.

M-34: an *incidental* uncited number (e.g. a year) with every citation grounded
      must not cap confidence to 0.5.
L-43: verify_answer must emit a ``violations`` list that route_after_verify reads
      and retries on (previously the key was absent → retry never fired).
L-49: those violations carry severity «unsupported» so run_metrics counts them
      (previously unsupported_rate was always 0).
"""

from __future__ import annotations

from agent_service.run_metrics import compute_run_metrics
from agent_service.verifier import apply_verification, verify_answer
from agent_service.verifier_retry import route_after_verify

from kg_common import AnswerPayload, Citation, EvidenceRef


class _FakeStore:
    def __init__(self, known: list[str]) -> None:
        self._known = set(known)

    def get_node(self, node_id: str):  # type: ignore[no-untyped-def]
        return {"id": node_id} if node_id in self._known else None


def _payload(md: str, citations=None, *, conf: float = 0.9) -> AnswerPayload:
    return AnswerPayload(
        answer_markdown=md,
        citations=citations or [],
        gaps=[],
        contradictions=[],
        used_models=[],
        confidence=conf,
    )


def _grounded_cite(store_id: str = "ev:1") -> Citation:
    return Citation(marker="[1]", evidence=EvidenceRef(evidence_id=store_id, source_id="s"))


# --- M-34: incidental number + grounded citation → confidence untouched -----
def test_incidental_number_does_not_cap_when_all_grounded() -> None:
    store = _FakeStore(["ev:1"])
    ans = _payload("Метод предложен в 1998 году [1].", [_grounded_cite()], conf=0.9)
    out = apply_verification(store, ans)
    assert out.verifier_report["verified"] is True
    assert out.confidence == 0.9  # the year 1998 is incidental — no 0.5 cap


def test_measurable_uncited_number_still_caps() -> None:
    out = apply_verification(_FakeStore([]), _payload("Эффективность 95% достигается.", conf=0.9))
    assert out.verifier_report["numeric_validation"]["ok"] is False
    assert out.confidence is not None and out.confidence <= 0.5


# --- L-43/L-49: violations schema drives retry + metrics --------------------
def test_ungrounded_citation_emits_unsupported_violation() -> None:
    store = _FakeStore([])  # the cited node does not resolve
    report = verify_answer(store, _payload("Вывод сделан [1].", [_grounded_cite("ev:nope")]))
    vios = report["violations"]
    assert vios and all(v["severity"] == "unsupported" for v in vios)
    assert vios[0]["marker"] == "[1]"


def test_numeric_claim_emits_violation() -> None:
    report = verify_answer(_FakeStore([]), _payload("Твёрдость 148 HV повышается."))
    kinds = {v["kind"] for v in report["violations"]}
    assert "numeric_claim_without_evidence" in kinds


def test_route_after_verify_retries_on_real_report() -> None:
    report = verify_answer(_FakeStore([]), _payload("Вывод [1].", [_grounded_cite("ev:nope")]))
    decision = route_after_verify(report, attempts=0, max_attempts=3)
    assert decision.next_node == "query_planner"
    assert decision.attempts == 1
    assert decision.unresolved  # the offending violation ids surface


def test_run_metrics_counts_unsupported_from_report() -> None:
    report = verify_answer(_FakeStore([]), _payload("Вывод [1].", [_grounded_cite("ev:nope")]))
    metrics = compute_run_metrics({"verifier_report": report})
    assert metrics.unsupported_claims >= 1


def test_clean_answer_has_no_violations_and_no_retry() -> None:
    store = _FakeStore(["ev:1"])
    clean = _payload("Обратный осмос удаляет сульфаты [1].", [_grounded_cite()])
    report = verify_answer(store, clean)
    assert report["violations"] == []
    assert report["verified"] is True
    assert route_after_verify(report, attempts=0).next_node == "answer_synthesizer"
