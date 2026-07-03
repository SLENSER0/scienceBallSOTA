"""Tests for community-report export to JSON / Markdown (§11.15).

Constructs deterministic :class:`CommunityReportPayload` records directly (no store
needed — the payload schema is a frozen dataclass) and hand-checks the JSON round-trip,
the Markdown card layout (title / summary / findings / entities), the empty-section
placeholders and the determinism of both renderers.
"""

from __future__ import annotations

import json

from kg_retrievers.community_export import (
    CommunityExport,
    build_community_export,
    communities_from_json,
    communities_to_json,
    communities_to_markdown,
    community_to_markdown,
)
from kg_retrievers.community_payload import CommunityReportPayload


def _main_payload() -> CommunityReportPayload:
    """A fully-populated community: title, summary, two findings, four entities."""
    return CommunityReportPayload(
        community_id=5,
        level=1,
        title="Cluster #5",
        rank=4.0,
        summary="Steel and copper hardness cluster.",
        findings=["Сталь повышает твёрдость.", "Copper lowers it."],
        entity_ids=["mat-copper", "mat-steel", "prop-hardness", "tech-quench"],
        material_ids=["mat-copper", "mat-steel"],
        property_ids=["prop-hardness"],
        doc_ids=["paperA.pdf", "paperB.pdf"],
        build_id="build-2026-07-03",
        build_version="v1.2.0",
        created_at="2026-07-03T00:00:00Z",
    )


def _empty_payload() -> CommunityReportPayload:
    """A blank community: no title, no summary, no findings, no entities."""
    return CommunityReportPayload(
        community_id=7,
        level=0,
        title="",
        rank=0.0,
        summary="",
    )


def test_json_round_trip() -> None:
    payloads = [_main_payload(), _empty_payload()]
    text = communities_to_json(payloads)
    # raw JSON decodes to the exact list of §9.8 as_dict mappings
    assert json.loads(text) == [p.as_dict() for p in payloads]
    # and the typed helper rebuilds the identical frozen payloads
    assert communities_from_json(text) == payloads
    # RU text survives verbatim (ensure_ascii=False), never \u-escaped
    assert "Сталь повышает твёрдость." in text
    assert "\\u" not in text


def test_json_empty_list_is_empty_array() -> None:
    assert communities_to_json([]) == "[]"
    assert communities_from_json("[]") == []


def test_markdown_has_title_and_summary() -> None:
    md = community_to_markdown(_main_payload())
    lines = md.splitlines()
    # the first line is the H1 title heading; the summary is its own paragraph
    assert lines[0] == "# Cluster #5"
    assert "Steel and copper hardness cluster." in lines
    assert md.endswith("\n")


def test_findings_rendered_as_bullets() -> None:
    md = community_to_markdown(_main_payload())
    assert "## Findings" in md
    # every finding appears verbatim as its own Markdown bullet, RU preserved
    assert "- Сталь повышает твёрдость." in md
    assert "- Copper lowers it." in md


def test_entities_listed_as_bullets() -> None:
    md = community_to_markdown(_main_payload())
    assert "## Entities" in md
    # every member entity id is listed as a bullet, in payload order
    for eid in ["mat-copper", "mat-steel", "prop-hardness", "tech-quench"]:
        assert f"- {eid}" in md
    ent_start = md.index("## Entities")
    ordered = md[ent_start:]
    assert ordered.index("mat-copper") < ordered.index("mat-steel")


def test_empty_findings_and_entities_use_placeholder() -> None:
    md = community_to_markdown(_empty_payload())
    # blank title falls back to a stable "Community {id}" heading
    assert md.startswith("# Community 7\n")
    # headings are still emitted, each followed by the _None_ placeholder
    assert "## Findings\n\n_None_" in md
    assert "## Entities\n\n_None_" in md
    # no stray bullets when there is nothing to list
    assert "- " not in md


def test_full_markdown_card_is_exact() -> None:
    payload = _main_payload()
    expected = (
        "# Cluster #5\n"
        "\n"
        "Steel and copper hardness cluster.\n"
        "\n"
        "## Findings\n"
        "\n"
        "- Сталь повышает твёрдость.\n"
        "- Copper lowers it.\n"
        "\n"
        "## Entities\n"
        "\n"
        "- mat-copper\n"
        "- mat-steel\n"
        "- prop-hardness\n"
        "- tech-quench\n"
    )
    assert community_to_markdown(payload) == expected


def test_renderers_are_deterministic() -> None:
    payloads = [_main_payload(), _empty_payload()]
    # identical inputs → byte-identical outputs across repeated calls
    assert communities_to_json(payloads) == communities_to_json(payloads)
    assert communities_to_markdown(payloads) == communities_to_markdown(payloads)
    # two independently-built equal payloads render identically
    assert community_to_markdown(_main_payload()) == community_to_markdown(_main_payload())


def test_communities_to_markdown_joins_cards_with_rule() -> None:
    payloads = [_main_payload(), _empty_payload()]
    doc = communities_to_markdown(payloads)
    # both cards are present, separated by a horizontal rule
    assert "# Cluster #5" in doc
    assert "# Community 7" in doc
    assert "\n---\n\n" in doc
    assert doc.count("# ") >= 2
    assert communities_to_markdown([]) == ""


def test_build_community_export_bundle() -> None:
    payloads = [_main_payload(), _empty_payload()]
    export = build_community_export(payloads)
    assert isinstance(export, CommunityExport)
    # bundle preserves input order and mirrors the standalone renderers
    assert export.as_dict() == {"communities": [p.as_dict() for p in payloads]}
    assert export.to_json() == communities_to_json(payloads)
    assert export.to_markdown() == communities_to_markdown(payloads)
    # frozen dataclass stores payloads as a tuple
    assert export.payloads == tuple(payloads)
