"""OpenSearch BM25 keyword store — server-profile keyword backend (§4.6).

§4.6 specifies OpenSearch as the *server-profile* keyword store (the embedded
profile uses the in-process ``rank_bm25`` :class:`~kg_retrievers.keyword_store`).
This module is the real thing: a thin client over a live OpenSearch cluster that

* creates the index from :func:`kg_retrievers.keyword_schema.build_index_mapping`
  (the ``scientific_text`` analyzer + text/keyword/numeric fields) — idempotently;
* bulk-indexes chunks (``id`` → ``_id``, remaining fields → ``_source``);
* searches the analyzed :data:`~kg_retrievers.keyword_schema.TEXT_FIELDS` with a
  ``multi_match`` and optional exact keyword ``filter`` narrowing;
* deletes every chunk of a source document and counts the live corpus.

Security on the local cluster is disabled, so the client connects unauthenticated
(``OpenSearch(hosts=[{"host": ..., "port": ...}])``). RU/EN текст analysed через
the ``scientific_text`` анализатор so Cyrillic queries (``обратный осмос``) match.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from opensearchpy import OpenSearch, helpers

from kg_common import get_logger, get_settings

from .keyword_schema import TEXT_FIELDS, build_index_mapping

_log = get_logger("opensearch_store")

# Default index name for the server-profile chunk corpus (§4.6).
DEFAULT_INDEX = "kg_chunks"


class OpenSearchKeywordStore:
    """BM25 keyword store backed by a live OpenSearch cluster (§4.6).

    Connects to ``url`` (default :attr:`Settings.opensearch_url`) and operates on a
    single ``index`` (default :data:`DEFAULT_INDEX`). Security is disabled on the
    local cluster, so no credentials are sent. All write paths refresh eagerly so a
    subsequent :meth:`search`/:meth:`count` observes the change immediately.
    """

    def __init__(self, url: str | None = None, index: str | None = None) -> None:
        self.url = url or get_settings().opensearch_url
        self.index = index or DEFAULT_INDEX
        parsed = urlparse(self.url)
        self.client = OpenSearch(
            hosts=[{"host": parsed.hostname or "localhost", "port": parsed.port or 9200}],
            http_compress=True,
            use_ssl=parsed.scheme == "https",
            verify_certs=False,
            ssl_show_warn=False,
        )

    # -- lifecycle --------------------------------------------------------
    def ping(self) -> bool:
        """``True`` if the cluster answers — used to gate live tests (§4.6)."""
        return bool(self.client.ping())

    def ensure_index(self) -> bool:
        """Create the index from :func:`build_index_mapping`, idempotently (§4.6).

        Returns ``True`` if the index was created, ``False`` if it already existed
        (a no-op second call). The body carries the ``scientific_text`` analyzer and
        the text/keyword/numeric field mapping so RU/EN text is analysed server-side.
        """
        if self.client.indices.exists(index=self.index):
            return False
        self.client.indices.create(index=self.index, body=build_index_mapping())
        _log.info("created OpenSearch index %s", self.index)
        return True

    def drop_index(self) -> None:
        """Delete the index if present (ignore 404) — teardown helper (§4.6)."""
        self.client.indices.delete(index=self.index, ignore=[404])

    # -- writes -----------------------------------------------------------
    def index_chunks(self, chunks: list[dict[str, Any]]) -> int:
        """Bulk-index ``chunks`` and refresh so they are instantly searchable (§4.6).

        Each chunk is a mapping with at least ``id`` (used as the document ``_id``)
        and ``text``; extra fields (``doc_id``, ``page``, keyword facets like
        ``domain``) land in ``_source`` verbatim. Returns the number of successfully
        indexed documents. ``refresh=True`` makes the writes visible right away.
        """
        actions = [{"_index": self.index, "_id": chunk["id"], **chunk} for chunk in chunks]
        if not actions:
            return 0
        success, _errors = helpers.bulk(self.client, actions, refresh=True)
        return int(success)

    def delete_by_doc(self, doc_id: str) -> int:
        """Delete every chunk whose ``doc_id`` equals ``doc_id``; refresh (§4.6).

        ``doc_id`` is dynamically mapped as ``text`` with a ``.keyword`` sub-field, so
        the exact term match runs against ``doc_id.keyword``. Returns the number of
        deleted documents; refresh keeps :meth:`count`/:meth:`search` consistent.
        """
        resp = self.client.delete_by_query(
            index=self.index,
            body={"query": {"term": {"doc_id.keyword": doc_id}}},
            refresh=True,
        )
        return int(resp.get("deleted", 0))

    def count_by_doc(self, doc_id: str) -> int | None:
        """Indexed-chunk count for one document; ``None`` if the index is absent (§4.6)."""
        try:
            resp = self.client.count(
                index=self.index, body={"query": {"term": {"doc_id.keyword": doc_id}}}
            )
            return int(resp["count"])
        except Exception:  # index_not_found / connection → unknown (not zero)
            return None

    # -- reads ------------------------------------------------------------
    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """BM25-rank the analyzed text fields for ``query`` (§4.6).

        Runs a ``multi_match`` over :data:`TEXT_FIELDS` (``name``, ``aliases_text``,
        ``text``). ``filters`` maps a keyword facet field (e.g. ``domain``) to an
        exact value and narrows the result set via a ``bool.filter`` term clause
        without affecting scoring. Returns up to ``top_k`` hits, best-scored first,
        each a dict ``{id, text, score, doc_id, page}``.
        """
        bool_query: dict[str, Any] = {
            "must": [{"multi_match": {"query": query, "fields": list(TEXT_FIELDS)}}]
        }
        if filters:
            bool_query["filter"] = [{"term": {field: value}} for field, value in filters.items()]
        resp = self.client.search(
            index=self.index,
            body={"size": top_k, "query": {"bool": bool_query}},
        )
        hits = resp["hits"]["hits"]
        return [
            {
                "id": hit["_source"].get("id", hit["_id"]),
                "text": hit["_source"].get("text", ""),
                "score": hit["_score"],
                "doc_id": hit["_source"].get("doc_id"),
                "page": hit["_source"].get("page"),
            }
            for hit in hits
        ]

    def count(self) -> int:
        """Number of live documents in the index (0 if it is empty) (§4.6)."""
        return int(self.client.count(index=self.index)["count"])
