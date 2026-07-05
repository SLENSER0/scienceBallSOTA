"""article_id keying: DOI → normalized URL (collision-free) → title.

Guards the 10-agent-verify fix: keying a DOI-less web source by title merged different
URLs with the same title; keying it via make_id collapsed '-./_' separators so distinct
URLs ('a-b.com' vs 'a.b.com', '/a/b' vs '/a-b') hashed to the same :Paper id.
"""

from __future__ import annotations

from kg_common.manual_article import ManualArticle, article_id


def _id(url: str = "", title: str = "T", doi: str = "") -> str:
    return article_id(ManualArticle(title=title, url=url, doi=doi))


def test_same_url_same_id_regardless_of_title() -> None:
    assert _id("https://h.com/paper/1", title="A") == _id("https://h.com/paper/1", title="B")


def test_url_normalization_is_idempotent() -> None:
    base = _id("https://h.com/paper/1")
    assert _id("https://h.com/paper/1/") == base  # trailing slash
    assert _id("https://h.com/paper/1#sec") == base  # fragment
    assert _id("https://H.COM/paper/1") == base  # host case
    assert _id("https://h.com:443/paper/1") == base  # default port


def test_distinct_urls_do_not_collide() -> None:
    # separators must not collapse (regression: canonical_key merged '-', '.', '/')
    assert _id("https://a-b.com/x") != _id("https://a.b.com/x")
    assert _id("https://h.com/a/b") != _id("https://h.com/a-b")
    assert _id("https://h.com/report.pdf") != _id("https://h.com/report-pdf")


def test_doi_wins_over_url() -> None:
    assert _id("https://h.com/x", doi="10.1/z") != _id("https://h.com/x")


def test_non_http_falls_back_to_title() -> None:
    assert _id("javascript:alert(1)", title="X") == article_id(ManualArticle(title="X"))
    assert _id("", title="X") == article_id(ManualArticle(title="X"))
    assert _id("not-a-url", title="X") == article_id(ManualArticle(title="X"))
