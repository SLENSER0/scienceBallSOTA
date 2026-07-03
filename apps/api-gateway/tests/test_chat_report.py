"""Tests for chat-message report export (§14.4).

Hermetic and dependency-free. Every assertion is hand-checkable: safe empty
defaults for missing artifacts, Markdown section headers and the summary text,
the experiments Markdown table header ``| id |``, the ``_none_`` placeholder for
empty sections, and the JSON-dict shape (``session_id`` string, ``experiments``
list) mirroring :meth:`ChatReport.as_dict`.
"""

from __future__ import annotations

from api_gateway.chat_report import (
    ChatReport,
    build_report,
    to_json_dict,
    to_markdown,
)


def _sample() -> ChatReport:
    return build_report(
        "s",
        "m",
        {
            "question": "What drives yield?",
            "summary": "Temperature dominates the observed yield.",
            "experiments": [{"id": "e1", "name": "run-A"}, {"id": "e2", "name": "run-B"}],
            "evidence": [{"doc": "d1"}],
            "graph": {"nodes": 3, "edges": 2},
            "gaps": [],
            "contradictions": [{"a": "e1", "b": "e2"}],
        },
    )


def test_missing_artifacts_default_to_empty() -> None:
    rep = build_report("s", "m", {})
    assert rep.experiments == ()
    assert rep.evidence == ()
    assert rep.gaps == ()
    assert rep.contradictions == ()
    assert rep.graph == {}
    assert rep.question == ""
    assert rep.summary == ""


def test_as_dict_serialises_tuples_as_lists() -> None:
    rep = _sample()
    d = rep.as_dict()
    assert isinstance(d["experiments"], list)
    assert isinstance(d["evidence"], list)
    assert d["session_id"] == "s"
    assert d["message_id"] == "m"
    assert d["graph"] == {"nodes": 3, "edges": 2}


def test_to_json_dict_matches_as_dict() -> None:
    rep = _sample()
    assert to_json_dict(rep) == rep.as_dict()
    assert to_json_dict(rep)["session_id"] == "s"
    assert isinstance(to_json_dict(rep)["experiments"], list)


def test_markdown_has_summary_section_and_text() -> None:
    rep = _sample()
    md = to_markdown(rep)
    assert "## Summary" in md
    assert "Temperature dominates the observed yield." in md


def test_markdown_experiments_table_header() -> None:
    rep = _sample()
    md = to_markdown(rep)
    assert "## Experiments" in md
    assert "| id |" in md
    assert "| e1 |" in md


def test_markdown_empty_gaps_renders_none() -> None:
    rep = _sample()
    md = to_markdown(rep)
    gaps_block = md.split("## Gaps", 1)[1]
    assert "_none_" in gaps_block


def test_markdown_has_all_section_headers() -> None:
    rep = _sample()
    md = to_markdown(rep)
    for header in (
        "## Summary",
        "## Experiments",
        "## Evidence",
        "## Graph",
        "## Gaps",
        "## Contradictions",
    ):
        assert header in md


def test_empty_report_markdown_all_none() -> None:
    md = to_markdown(build_report("s", "m", {}))
    # summary, experiments, evidence, graph, gaps, contradictions all empty.
    assert md.count("_none_") == 6
    assert "## Contradictions" in md
