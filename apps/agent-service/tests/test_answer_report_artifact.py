"""Hand-checked tests for §13.17 exportable report artifact.

Pure-python, no store / no LLM: hand :func:`build_report` an ``AnswerPayload``-like
dict and assert the exact markdown shape — section order, the experiments pipe table,
the ``ev:<id>`` citation lines, and the omit-when-empty rule. Every expected string is
spelled out so the test is verifiable by hand.
"""

from __future__ import annotations

from agent_service.answer_report_artifact import ReportArtifact, build_report


def _full_answer() -> dict:
    """A full AnswerPayload-like dict exercising every section."""
    return {
        "summary": "Кремний упрочняется отжигом.",
        "experiments": [
            {
                "material": "Si",
                "processing": "anneal 900C",
                "property": "hardness",
                "value": "12",
                "unit": "GPa",
                "effect": "increase",
                "confidence": "0.8",
                "evidence_ids": ["a", "b"],
            },
            {
                "material": "SiC",
                "processing": "sinter",
                "property": "modulus",
                "value": "410",
                "unit": "GPa",
                "effect": "none",
                "confidence": "0.6",
                "evidence_ids": ["c"],
            },
        ],
        "evidence": [{"id": "a"}],
        "gaps": ["missing hardness at 1200C"],
        "contradictions": ["ev:a vs ev:b"],
        "citations": ["e1", "e2"],
    }


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------
def test_summary_heading_and_text_present() -> None:
    art = build_report({"summary": "Кремний упрочняется отжигом."})
    assert "## Summary" in art.markdown
    assert "Кремний упрочняется отжигом." in art.markdown
    assert art.sections == ("Summary",)


# ---------------------------------------------------------------------------
# experiments table
# ---------------------------------------------------------------------------
def test_experiments_header_and_one_row_per_experiment() -> None:
    art = build_report(_full_answer())
    lines = art.markdown.splitlines()
    header = next(ln for ln in lines if "material | processing" in ln)
    assert header == (
        "| material | processing | property | value | unit | effect | confidence | evidence_ids |"
    )
    # exactly one data row per experiment (two here), each carrying its material.
    data_rows = [ln for ln in lines if ln.startswith("| Si ") or ln.startswith("| SiC ")]
    assert len(data_rows) == 2


def test_evidence_ids_list_joined_by_comma() -> None:
    art = build_report(_full_answer())
    # the two-element evidence_ids list renders joined as 'a,b'.
    assert "a,b" in art.markdown
    # the single-element list renders as just 'c' (no trailing comma).
    row_c = next(ln for ln in art.markdown.splitlines() if ln.startswith("| SiC "))
    assert row_c.rstrip().endswith("| c |")


def test_empty_experiments_omits_section() -> None:
    art = build_report({"summary": "s", "experiments": []})
    assert "## Experiments" not in art.markdown
    assert "Experiments" not in art.sections


# ---------------------------------------------------------------------------
# citations
# ---------------------------------------------------------------------------
def test_citations_render_as_ev_lines() -> None:
    art = build_report({"citations": ["e1"]})
    assert "- ev:e1" in art.markdown.splitlines()
    assert art.sections == ("Citations",)


# ---------------------------------------------------------------------------
# section order + omit-when-empty
# ---------------------------------------------------------------------------
def test_full_payload_section_order() -> None:
    art = build_report(_full_answer())
    assert art.sections == ("Summary", "Experiments", "Gaps", "Contradictions", "Citations")


def test_empty_answer_emits_nothing() -> None:
    art = build_report({})
    assert art.markdown == ""
    assert art.sections == ()


def test_gaps_and_contradictions_bullets() -> None:
    art = build_report({"gaps": ["g one"], "contradictions": ["c one", "c two"]})
    lines = art.markdown.splitlines()
    assert "## Gaps" in lines
    assert "- g one" in lines
    assert "## Contradictions" in lines
    assert "- c one" in lines
    assert "- c two" in lines
    assert art.sections == ("Gaps", "Contradictions")


# ---------------------------------------------------------------------------
# dataclass
# ---------------------------------------------------------------------------
def test_report_artifact_as_dict_roundtrips_markdown() -> None:
    art = build_report(_full_answer())
    d = art.as_dict()
    assert d["markdown"] == art.markdown
    assert d["sections"] == list(art.sections)
    assert isinstance(d["sections"], list)


def test_report_artifact_is_frozen() -> None:
    art = ReportArtifact(markdown="x", sections=("Summary",))
    try:
        art.markdown = "y"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - dataclass(frozen=True) must forbid assignment
        raise AssertionError("ReportArtifact must be frozen")
