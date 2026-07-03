"""Hand-checked tests for §13.14 answer assembly.

Pure-python, no store / no LLM: hand the assembler already-prepared parts and
assert the exact camelCase §5.3 shape — every expected value is spelled out so the
test is verifiable by hand. The final dict is also round-tripped through
:class:`kg_common.AnswerPayload` to prove the keys match the contract.
"""

from __future__ import annotations

import pytest
from agent_service.answer_assembler import AssembledAnswer, assemble_answer

from kg_common import AnswerPayload, Citation, EvidenceRef, GraphNode, GraphResponse

# The exact key set the assembler emits (seven of the ten §5.3 aliases).
_EXPECTED_KEYS = {
    "answerMarkdown",
    "citations",
    "graph",
    "gaps",
    "contradictions",
    "confidence",
    "usedModels",
}

# All camelCase aliases of the AnswerPayload contract (§5.3).
_PAYLOAD_ALIASES = {(f.alias or n) for n, f in AnswerPayload.model_fields.items()}


def _citation(evidence_id: str = "ev:1") -> Citation:
    """Build a kg_common Citation (CamelModel) for the assembler to normalise."""
    return Citation(
        marker="[1]",
        evidence=EvidenceRef(evidence_id=evidence_id, source_id="claim:x", doc_id="doc:p1", page=3),
        source_title="Paper A",
        year=2021,
    )


# ---------------------------------------------------------------------------
# key set / camelCase
# ---------------------------------------------------------------------------
def test_all_keys_present_and_camelcase() -> None:
    result = assemble_answer(answer_markdown="Ответ.", citations=[])
    assert set(result) == _EXPECTED_KEYS
    # every emitted key is a valid §5.3 AnswerPayload alias (no stray keys).
    assert set(result).issubset(_PAYLOAD_ALIASES)
    # snake_case names must NOT leak into the payload.
    assert "answer_markdown" not in result
    assert "used_models" not in result


def test_defaults_for_missing_parts() -> None:
    # Only the two required parts supplied → optionals collapse to DTO defaults.
    result = assemble_answer(answer_markdown="hi", citations=[])
    assert result == {
        "answerMarkdown": "hi",
        "citations": [],
        "graph": None,
        "gaps": [],
        "contradictions": [],
        "confidence": None,
        "usedModels": [],
    }


# ---------------------------------------------------------------------------
# passthrough / defaults for individual fields
# ---------------------------------------------------------------------------
def test_confidence_passthrough_verbatim() -> None:
    # A given confidence is passed through unchanged (no clamping to [0, 1]).
    assert assemble_answer(answer_markdown="x", citations=[], confidence=0.83)["confidence"] == 0.83
    assert assemble_answer(answer_markdown="x", citations=[], confidence=1.5)["confidence"] == 1.5
    # Omitted confidence is None, not 0.0.
    assert assemble_answer(answer_markdown="x", citations=[])["confidence"] is None


def test_used_models_is_a_list_copy() -> None:
    models = ["qwen2.5", "bge-m3"]
    result = assemble_answer(answer_markdown="x", citations=[], used_models=models)
    assert result["usedModels"] == ["qwen2.5", "bge-m3"]
    # a fresh list — mutating the input afterwards must not touch the payload.
    models.append("leaked")
    assert result["usedModels"] == ["qwen2.5", "bge-m3"]


def test_empty_answer_markdown_tolerated() -> None:
    # An empty answer string is a valid (if empty) answer — not coerced away.
    result = assemble_answer(answer_markdown="", citations=[])
    assert result["answerMarkdown"] == ""


# ---------------------------------------------------------------------------
# citations (required) + normalisation
# ---------------------------------------------------------------------------
def test_citations_are_required_keyword() -> None:
    with pytest.raises(TypeError):
        assemble_answer(answer_markdown="x")  # type: ignore[call-arg]


def test_citations_model_normalised_to_camelcase_dicts() -> None:
    result = assemble_answer(answer_markdown="Вывод [1].", citations=[_citation("ev:1")])
    assert len(result["citations"]) == 1
    cit = result["citations"][0]
    assert cit["marker"] == "[1]"
    assert cit["sourceTitle"] == "Paper A"
    assert cit["year"] == 2021
    # nested EvidenceRef is dumped by_alias too (evidence_id → evidenceId).
    assert cit["evidence"]["evidenceId"] == "ev:1"
    assert cit["evidence"]["docId"] == "doc:p1"
    assert cit["evidence"]["page"] == 3


def test_citations_plain_dicts_passed_through() -> None:
    src = {"marker": "[2]", "sourceTitle": "Manual"}
    result = assemble_answer(answer_markdown="x", citations=[src])
    assert result["citations"] == [{"marker": "[2]", "sourceTitle": "Manual"}]
    # shallow copy — the payload does not alias the caller's dict.
    assert result["citations"][0] is not src


# ---------------------------------------------------------------------------
# graph (optional) + gaps / contradictions
# ---------------------------------------------------------------------------
def test_graph_optional_none() -> None:
    assert assemble_answer(answer_markdown="x", citations=[])["graph"] is None


def test_graph_model_dumped_by_alias() -> None:
    graph = GraphResponse(nodes=[GraphNode(id="n1", label="Кремний", type="Material")])
    result = assemble_answer(answer_markdown="x", citations=[], graph=graph)
    assert set(result["graph"]) == {"nodes", "edges", "layoutHints", "queryContext"}
    assert result["graph"]["nodes"][0]["id"] == "n1"
    assert result["graph"]["nodes"][0]["label"] == "Кремний"
    assert result["graph"]["edges"] == []


def test_gaps_and_contradictions_passthrough() -> None:
    gaps = [{"kind": "missing_property", "field": "hardness"}]
    contradictions = [{"claimA": "c1", "claimB": "c2"}]
    result = assemble_answer(
        answer_markdown="x",
        citations=[],
        gaps=gaps,
        contradictions=contradictions,
    )
    assert result["gaps"] == [{"kind": "missing_property", "field": "hardness"}]
    assert result["contradictions"] == [{"claimA": "c1", "claimB": "c2"}]


# ---------------------------------------------------------------------------
# contract round-trip + dataclass
# ---------------------------------------------------------------------------
def test_result_roundtrips_through_answer_payload() -> None:
    result = assemble_answer(
        answer_markdown="Итог [1].",
        citations=[_citation("ev:1")],
        graph=GraphResponse(nodes=[GraphNode(id="n1", label="X", type="Material")]),
        gaps=[{"kind": "missing"}],
        confidence=0.7,
        used_models=["qwen2.5"],
    )
    # The emitted camelCase dict validates cleanly against the §5.3 contract.
    payload = AnswerPayload.model_validate(result)
    assert payload.answer_markdown == "Итог [1]."
    assert payload.confidence == 0.7
    assert payload.used_models == ["qwen2.5"]
    assert payload.gaps == [{"kind": "missing"}]
    assert payload.citations[0].marker == "[1]"
    assert payload.citations[0].evidence.evidence_id == "ev:1"
    assert payload.graph is not None
    assert payload.graph.nodes[0].id == "n1"


def test_assembled_answer_dataclass_as_dict() -> None:
    parts = AssembledAnswer(
        answer_markdown="a",
        citations=[{"marker": "[1]"}],
        graph=None,
        gaps=[],
        contradictions=[],
        confidence=0.5,
        used_models=["m"],
    )
    assert parts.as_dict() == {
        "answerMarkdown": "a",
        "citations": [{"marker": "[1]"}],
        "graph": None,
        "gaps": [],
        "contradictions": [],
        "confidence": 0.5,
        "usedModels": ["m"],
    }
    # frozen — attributes cannot be reassigned.
    with pytest.raises(AttributeError):
        parts.confidence = 0.9  # type: ignore[misc]
