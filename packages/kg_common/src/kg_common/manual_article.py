"""Manual article ingestion into the knowledge graph (§5 / library).

Turns a hand-entered (or deep-research-picked) article into a ``:Paper`` node plus,
when an abstract/text is supplied, one ``:Chunk`` and an evidence-first ``:Evidence``
linked by ``FROM_CHUNK``. Deterministic ids (from DOI or title) make re-adding the
same article idempotent. This is the human-curated counterpart to the automated
ingestion pipeline; it writes through the same graph-store interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kg_common.ids import make_id, uuid5_id


@dataclass(frozen=True)
class ManualArticle:
    """A manually-submitted article (only ``title`` is required)."""

    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    doi: str = ""
    url: str = ""
    source: str = ""  # provider id, e.g. "mdpi" / "elibrary" / "manual"
    abstract: str = ""
    domain: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "authors": list(self.authors),
            "year": self.year,
            "doi": self.doi,
            "url": self.url,
            "source": self.source,
            "abstract": self.abstract,
            "domain": self.domain,
        }


def article_id(article: ManualArticle) -> str:
    """Deterministic Paper id — from DOI when present, else the title."""
    key = article.doi.strip() or article.title.strip()
    return make_id("Paper", key, use_hash=bool(article.doi))


def validate_article(article: ManualArticle) -> list[str]:
    """Return a list of validation errors ([] when valid)."""
    errors: list[str] = []
    if not article.title.strip():
        errors.append("title is required")
    if article.year is not None and not (1800 <= article.year <= 2100):
        errors.append("year out of range")
    if article.url and not article.url.lower().startswith(("http://", "https://")):
        errors.append("url must be http(s)")
    return errors


def build_paper_node(article: ManualArticle) -> dict[str, Any]:
    """Build the ``:Paper`` node props for :meth:`GraphStore.upsert_node`."""
    pid = article_id(article)
    props: dict[str, Any] = {
        "name": article.title.strip(),
        "canonical_name": article.title.strip(),
        "year": article.year,
        "doi": article.doi.strip() or None,
        "url": article.url.strip() or None,
        "source": article.source or "manual",
        "authors_text": ", ".join(article.authors) or None,
        "domain": article.domain or None,
        "review_status": "manual",
        "evidence_strength": "manual",
        "extractor_run_id": "manual_add",
    }
    return {"id": pid, "label": "Paper", "props": {k: v for k, v in props.items() if v is not None}}


def build_graph_ops(article: ManualArticle) -> dict[str, Any]:
    """Full write plan for a manual article: the Paper node + optional abstract chunk.

    Returns ``{nodes: [...], edges: [...]}`` where each node is
    ``{id, label, props}`` and each edge is ``{src, dst, type, props}``. When an
    abstract is present, a ``:Chunk`` (the abstract text) and an ``:Evidence`` are
    added and wired ``Paper -HAS_CHUNK-> Chunk`` and ``Evidence -FROM_CHUNK-> Chunk``.
    """
    paper = build_paper_node(article)
    nodes = [paper]
    edges: list[dict[str, Any]] = []
    if article.abstract.strip():
        cid = uuid5_id("Chunk", paper["id"], "abstract")
        nodes.append(
            {
                "id": cid,
                "label": "Chunk",
                "props": {
                    "text": article.abstract.strip(),
                    "doc_id": paper["id"],
                    "section": "abstract",
                    "extractor_run_id": "manual_add",
                },
            }
        )
        edges.append({"src": paper["id"], "dst": cid, "type": "HAS_CHUNK", "props": {}})
        eid = uuid5_id("Evidence", cid, "abstract")
        nodes.append(
            {
                "id": eid,
                "label": "Evidence",
                "props": {
                    "doc_id": paper["id"],
                    "text": article.abstract.strip()[:400],
                    "source_type": "paragraph",
                    "review_status": "manual",
                    "extractor_run_id": "manual_add",
                },
            }
        )
        edges.append({"src": eid, "dst": cid, "type": "FROM_CHUNK", "props": {}})
    return {"paper_id": paper["id"], "nodes": nodes, "edges": edges}
