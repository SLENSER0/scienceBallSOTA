"""Canonical parsed-artifact object-storage keys for one document (§5.5).

§5.5 fixes the exact object-storage layout for a single ingested document:
the raw upload lands in the ``kg-raw`` bucket, and every parsed artifact
(Docling JSON, Markdown, per-table / per-image / per-page shards, the chunk
stream and the manifest — таблицы, изображения, страницы, чанки, манифест)
lands in the ``kg-parsed`` bucket under a stable ``documents/doc:<id>/`` prefix.

These are *pure* key builders — no I/O. Counters (NNN) zero-pad to width 3 and
start at 1; ``n < 1`` raises ``ValueError`` (нумерация с единицы, §5.5).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

__all__ = ["DocumentArtifactPaths"]

# Common prefix for one document's keys (общий префикс ключей документа, §5.5).
_PREFIX = "documents/doc:{doc_id}"


def _counter(n: int) -> str:
    """Zero-pad a 1-based counter to width 3, rejecting ``n < 1`` (§5.5)."""
    if n < 1:
        raise ValueError(f"counter must be >= 1 (нумерация с единицы), got {n}")
    return f"{n:03d}"


@dataclass(frozen=True)
class DocumentArtifactPaths:
    """Builds the exact §5.5 object-storage keys for one document.

    Строит канонические ключи объектного хранилища для одного документа.
    """

    doc_id: str
    ext: str
    raw_bucket: str = "kg-raw"
    parsed_bucket: str = "kg-parsed"

    def as_dict(self) -> dict[str, Any]:
        """Return the frozen fields as a plain dict (fields incl. bucket names)."""
        return asdict(self)

    @property
    def _base(self) -> str:
        """The ``documents/doc:<id>`` prefix shared by every key (§5.5)."""
        return _PREFIX.format(doc_id=self.doc_id)

    def raw_key(self) -> str:
        """Key of the raw upload in ``raw_bucket`` (сырой документ, §5.5)."""
        return f"{self._base}/original.{self.ext}"

    def docling_json_key(self) -> str:
        """Key of the Docling parse result (структурированный разбор, §5.5)."""
        return f"{self._base}/docling.json"

    def markdown_key(self) -> str:
        """Key of the rendered Markdown document (§5.5)."""
        return f"{self._base}/document.md"

    def table_key(self, n: int) -> str:
        """Key of the ``n``-th extracted table shard (1-based, §5.5)."""
        return f"{self._base}/tables/table_{_counter(n)}.json"

    def image_key(self, n: int) -> str:
        """Key of the ``n``-th extracted image (1-based, §5.5)."""
        return f"{self._base}/images/img_{_counter(n)}.png"

    def page_key(self, n: int) -> str:
        """Key of the ``n``-th per-page shard (1-based, §5.5)."""
        return f"{self._base}/pages/page_{_counter(n)}.json"

    def chunks_key(self) -> str:
        """Key of the JSONL chunk stream (поток чанков, §5.5)."""
        return f"{self._base}/chunks.jsonl"

    def manifest_key(self) -> str:
        """Key of the per-document manifest (манифест документа, §5.5)."""
        return f"{self._base}/manifest.json"
