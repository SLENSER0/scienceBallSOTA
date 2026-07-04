"""Grounding-hardening behaviour in synthesize + verifier (benchmark follow-up).

Covers: OCR-junk citations are dropped, a corpus with no readable support yields a
deterministic grounded refusal instead of a fabricated answer, confidence tracks the
amount of clean support (no longer flat ~0.49), gaps are scoped to the question, and
the verifier treats junk-text citations as unsupported.
"""

from __future__ import annotations

from agent_service.synthesize import build_answer
from agent_service.verifier import verify_answer

from kg_common import AnswerPayload, Citation, EvidenceRef
from kg_extractors.query_parser import QueryIntent
from kg_retrievers.graph_retriever import RetrievalResult


def _ev(eid: str, text: str, conf: float = 0.7) -> dict:
    return {"id": eid, "text": text, "confidence": conf, "doc_id": f"doc:{eid}"}


CLEAN1 = "Известковое молоко Ca(OH)2 осаждает тяжёлые металлы в виде гидроксидов при pH 9."
CLEAN2 = "Электродиализ снижает энергозатраты и работает при давлении менее семи бар."
JUNK1 = "(cid:20) ские сгустки органического вещества размером ды содержащей керогена"
JUNK2 = "0,147 мм . . . . . . . . . . . . . . . . . 2–4 ментов обусловлена реакций"


def test_ocr_junk_never_becomes_a_citation() -> None:
    intent = QueryIntent(raw="Очистка шахтных вод цветной металлургии")
    retr = RetrievalResult(
        intent=intent, evidence=[_ev("e1", CLEAN1), _ev("e2", JUNK1), _ev("e3", JUNK2)]
    )
    ans = build_answer(intent, retr, use_llm=False)
    assert len(ans.citations) == 1
    assert ans.citations[0].evidence.evidence_id == "e1"
    assert "cid:" not in (ans.citations[0].evidence.text or "")


def test_out_of_coverage_is_a_grounded_refusal_not_a_fabrication() -> None:
    intent = QueryIntent(raw="Закачка шахтных вод в глубокие горизонты")
    # only junk evidence, no facts/solutions/passages -> nothing readable to stand on
    retr = RetrievalResult(intent=intent, evidence=[_ev("e1", JUNK1), _ev("e2", JUNK2)])
    ans = build_answer(intent, retr, use_llm=True)  # LLM must be skipped by the guard
    assert ans.confidence == 0.1
    assert ans.citations == []
    assert "грунтованный отказ" in ans.answer_markdown
    assert ans.used_models == []


def test_confidence_tracks_clean_support() -> None:
    intent = QueryIntent(raw="Обессоливание воды обогатительной фабрики")
    rich = RetrievalResult(
        intent=intent,
        evidence=[_ev("e1", CLEAN1), _ev("e2", CLEAN2), _ev("e3", CLEAN1, 0.8)],
        solutions=[{"name": "Обратный осмос", "practice_type": "global"}],
    )
    junky = RetrievalResult(
        intent=intent,
        evidence=[_ev("e1", CLEAN1), _ev("e2", JUNK1), _ev("e3", JUNK2)],
    )
    empty = RetrievalResult(intent=intent)
    c_rich = build_answer(intent, rich, use_llm=False).confidence
    c_junky = build_answer(intent, junky, use_llm=False).confidence
    c_empty = build_answer(intent, empty, use_llm=False).confidence
    assert c_empty == 0.1  # grounded-refusal floor
    assert c_junky < c_rich  # noise drags confidence down
    assert 0.3 <= c_rich <= 0.9
    # the three inputs get three distinct scores — confidence is now calibrated,
    # not the old flat ~0.49 that ignored how much clean support the answer had
    assert len({c_empty, c_junky, c_rich}) == 3


def test_gaps_are_scoped_to_the_question() -> None:
    intent = QueryIntent(raw="Техногенный гипс: источники и переработка")
    retr = RetrievalResult(
        intent=intent,
        evidence=[_ev("e1", CLEAN1)],
        gaps=[
            {"name": "Переработка фосфогипса в стройматериалы", "gap_type": "true_gap"},
            {"name": "Плавка Ванюкова медного штейна", "gap_type": "true_gap"},
        ],
    )
    ans = build_answer(intent, retr, use_llm=False)
    names = [g["name"] for g in ans.gaps]
    assert any("фосфогипс" in n.lower() for n in names)
    assert not any("ванюков" in n.lower() for n in names)


class _FakeStore:
    def __init__(self, known: list[str]) -> None:
        self._known = set(known)

    def get_node(self, node_id: str):  # type: ignore[no-untyped-def]
        return {"id": node_id} if node_id in self._known else None


def _cite(marker: str, eid: str, text: str) -> Citation:
    return Citation(
        marker=marker,
        evidence=EvidenceRef(evidence_id=eid, source_id=eid, text=text, confidence=1.0),
        source_title=text[:60],
    )


def test_verifier_treats_junk_text_citation_as_unsupported() -> None:
    answer = AnswerPayload(
        answer_markdown="Осаждение металлов гидроксидами [1][2].",
        citations=[_cite("[1]", "e1", CLEAN1), _cite("[2]", "e2", JUNK1)],
        gaps=[],
        contradictions=[],
        used_models=[],
        confidence=0.8,
    )
    report = verify_answer(_FakeStore(["e1", "e2"]), answer)  # both nodes exist
    # e2 exists as a node but its text is OCR junk -> not real provenance
    assert "[2]" in report["unsupported"]
    assert "[1]" not in report["unsupported"]
    assert report["coverage"] == 0.5
