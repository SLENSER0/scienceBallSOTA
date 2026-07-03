"""§5 library: source catalog + deep-research planner + manual-article ops."""

from __future__ import annotations

from kg_common.deep_research import build_plan, extract_keywords
from kg_common.manual_article import (
    ManualArticle,
    article_id,
    build_graph_ops,
    validate_article,
)
from kg_common.research_sources import all_sources, get_source, search_url


def test_catalog_has_all_requested_sources() -> None:
    ids = {s["id"] for s in all_sources()}
    assert {
        "researchgate",
        "elibrary",
        "springer",
        "google_patents",
        "mdpi",
        "cyberleninka",
        "wiley",
        "sciencedirect",
        "scihub",
    } <= ids


def test_scihub_flagged_shadow() -> None:
    assert get_source("scihub").access == "shadow"
    assert get_source("mdpi").access == "open"


def test_search_url_encodes_query() -> None:
    url = search_url("mdpi", "обратный осмос сульфаты")
    assert url and url.startswith("https://www.mdpi.com/search?q=")
    assert "+" in url or "%" in url  # url-encoded
    assert search_url("unknown", "x") is None


def test_extract_keywords_drops_stopwords() -> None:
    kw = extract_keywords("методы очистки воды от сульфатов")
    assert "методы" in kw and "для" not in kw and "и" not in kw


def test_plan_decomposes_and_links_every_source() -> None:
    plan = build_plan("очистка воды от сульфатов", use_llm=False)
    assert plan.question and plan.keywords
    assert len(plan.sub_questions) >= 2
    # every sub-question links to the whole catalog
    n_sources = len(all_sources())
    for sq in plan.sub_questions:
        assert len(sq.links) == n_sources
    # as_dict round-trips
    d = plan.as_dict()
    assert d["sub_questions"][0]["links"][0]["url"].startswith("http")


def test_plan_can_limit_sources() -> None:
    plan = build_plan("сульфаты", source_ids=["mdpi", "cyberleninka"])
    assert all(len(sq.links) == 2 for sq in plan.sub_questions)


def test_manual_article_validation() -> None:
    assert validate_article(ManualArticle(title="")) == ["title is required"]
    assert validate_article(ManualArticle(title="X", year=1500)) == ["year out of range"]
    assert validate_article(ManualArticle(title="X", url="ftp://x")) == ["url must be http(s)"]
    assert validate_article(ManualArticle(title="Ok", year=2024)) == []


def test_article_id_deterministic() -> None:
    a = ManualArticle(title="Обратный осмос воды", doi="10.1/xyz")
    assert article_id(a) == article_id(a)
    # DOI drives the id: same DOI, different title → same id
    b = ManualArticle(title="Completely different", doi="10.1/xyz")
    assert article_id(a) == article_id(b)


def test_build_graph_ops_with_abstract() -> None:
    ops = build_graph_ops(
        ManualArticle(
            title="RO desalination", year=2023, abstract="Reverse osmosis removes sulfates."
        )
    )
    labels = [n["label"] for n in ops["nodes"]]
    assert "Paper" in labels and "Chunk" in labels and "Evidence" in labels
    types = [e["type"] for e in ops["edges"]]
    assert "HAS_CHUNK" in types and "FROM_CHUNK" in types
    assert ops["paper_id"].startswith("paper:")


def test_build_graph_ops_without_abstract_is_paper_only() -> None:
    ops = build_graph_ops(ManualArticle(title="Bare paper"))
    assert [n["label"] for n in ops["nodes"]] == ["Paper"]
    assert ops["edges"] == []
