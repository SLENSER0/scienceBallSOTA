"""Per-doctype OpenSearch indices — one index per document family (§4.6).

§4.6 ships a single ``kg_chunks`` corpus via
:func:`kg_retrievers.keyword_schema.build_index_mapping` (the ``scientific_text``
analyzer + shared text/keyword/numeric fields) indexed through
:class:`kg_retrievers.opensearch_store.OpenSearchKeywordStore`. Structured
extraction adds three more document families that want their own index so their
доменные поля are queryable server-side:

* ``kg_table_rows`` — one row of an extracted table (``table_id`` keyword,
  ``row_index`` / ``col_index`` integers);
* ``kg_claims`` — an extracted claim (``claim_type`` keyword, ``subject_id``
  keyword);
* ``kg_entities`` — an entity card (``entity_type`` keyword, ``aliases_text``
  analyzed text — RU/EN синонимы для полнотекстового поиска).

Each doctype index is the base mapping **plus** its distinctive fields, declared
here declaratively as :data:`INDEX_SPECS` (name → :class:`IndexSpec`). This module
builds *on* :mod:`keyword_schema` (the base body) and :mod:`opensearch_store` (its
live client) and edits neither: :func:`ensure_indices` idempotently creates all
four against the live cluster (default :attr:`Settings.opensearch_url`) and
:func:`drop_indices` tears a namespace back down.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from opensearchpy import OpenSearch

from kg_common import get_logger

from .keyword_schema import SCIENTIFIC_ANALYZER, build_index_mapping
from .opensearch_store import OpenSearchKeywordStore

_log = get_logger("opensearch_indices")


def _field_body(es_type: str) -> dict:
    """OpenSearch ``properties`` body for a single field of type ``es_type`` (§4.6).

    ``text`` fields are analyzed with :data:`SCIENTIFIC_ANALYZER` (so ``aliases_text``
    tokenises RU/EN identically to the base body); every other type (``keyword``,
    ``integer`` …) maps to the bare ``{"type": es_type}``.
    """
    if es_type == "text":
        return {"type": "text", "analyzer": SCIENTIFIC_ANALYZER.name}
    return {"type": es_type}


@dataclass(frozen=True)
class IndexSpec:
    """A per-doctype index: its name + the fields it adds over the base body (§4.6).

    ``extra_fields`` is a tuple of ``(field_name, es_type)`` pairs merged into the
    ``mappings.properties`` of :func:`build_index_mapping`. An empty tuple (the
    ``kg_chunks`` default) yields the plain base mapping unchanged.
    """

    name: str
    extra_fields: tuple[tuple[str, str], ...] = field(default=())

    def as_dict(self) -> dict:
        """The full OpenSearch create-index body (base + doctype fields) (§4.6).

        Starts from a fresh :func:`build_index_mapping` (independent dict each call)
        and overlays :attr:`extra_fields`, so building twice yields equal, independent
        bodies (idempotent). The base ``settings.analysis`` block is carried through.
        """
        body = build_index_mapping()
        props = body["mappings"]["properties"]
        for field_name, es_type in self.extra_fields:
            props[field_name] = _field_body(es_type)
        return body


# The four per-doctype indices (§4.6): kg_chunks is the plain base body; the other
# three add the fields that make their doctype queryable/facetable server-side.
INDEX_SPECS: dict[str, IndexSpec] = {
    "kg_chunks": IndexSpec("kg_chunks"),
    "kg_table_rows": IndexSpec(
        "kg_table_rows",
        extra_fields=(
            ("table_id", "keyword"),
            ("row_index", "integer"),
            ("col_index", "integer"),
        ),
    ),
    "kg_claims": IndexSpec(
        "kg_claims",
        extra_fields=(("claim_type", "keyword"), ("subject_id", "keyword")),
    ),
    "kg_entities": IndexSpec(
        "kg_entities",
        extra_fields=(("entity_type", "keyword"), ("aliases_text", "text")),
    ),
}


def _default_client() -> OpenSearch:
    """Live OpenSearch client at :attr:`Settings.opensearch_url` (§4.6).

    Reuses :class:`OpenSearchKeywordStore`'s connection setup (unauthenticated —
    security is disabled on the local cluster) rather than re-deriving host/port, so
    the default target stays in one place. The store's default index is irrelevant
    here; only its bound ``client`` is used.
    """
    return OpenSearchKeywordStore().client


def ensure_indices(client: OpenSearch | None = None, prefix: str = "") -> dict[str, bool]:
    """Idempotently create every :data:`INDEX_SPECS` index on the live cluster (§4.6).

    For each doctype the index name is ``f"{prefix}{name}"``. An existing index is a
    no-op; a missing one is created from :meth:`IndexSpec.as_dict`. ``client`` defaults
    to :func:`_default_client` (``Settings.opensearch_url``). ``prefix`` namespaces the
    indices so a test run (or a tenant) never collides with the canonical set.

    Returns ``{index_name: created}`` — ``created`` is ``True`` when this call created
    the index, ``False`` when it already existed. A second identical call therefore
    returns all-``False`` (idempotent).
    """
    client = client or _default_client()
    result: dict[str, bool] = {}
    for name, spec in INDEX_SPECS.items():
        index = f"{prefix}{name}"
        if client.indices.exists(index=index):
            result[index] = False
            continue
        client.indices.create(index=index, body=spec.as_dict())
        _log.info("created OpenSearch index %s", index)
        result[index] = True
    return result


def drop_indices(client: OpenSearch, names: Iterable[str]) -> None:
    """Delete each index in ``names`` if present, ignoring 404 — teardown helper (§4.6).

    Mirrors :meth:`OpenSearchKeywordStore.drop_index` for a batch: dropping an absent
    index is a no-op, so the call is safe to run in a test ``finally`` even when
    :func:`ensure_indices` never ran.
    """
    for name in names:
        client.indices.delete(index=name, ignore=[404])
