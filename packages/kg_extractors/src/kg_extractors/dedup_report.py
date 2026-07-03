"""Source-dedup report — group ingested documents by content hash (§5.12).

The *отчёт дедупликации источников* deliverable: given a flat list of already
parsed documents, each carrying an ``id`` and a ``content_hash`` (sha256 of the
raw bytes, §5.4), fold them into one auditable :class:`DedupReport` that tells a
curator exactly which uploads are byte-identical re-runs of an earlier one.

Grouping is **by ``content_hash``** (по хэшу содержимого). Within each hash
group the *first* document in input order is the **kept** original; every later
document sharing that hash is a **dropped** duplicate (idempotent upload should
have returned the existing ``source_id`` with ``duplicate=true`` — this report
surfaces the ones that slipped through). Input order is preserved throughout so
the numbers are stable and hand-checkable.

Report fields:

* ``total``      — number of documents fed in (всего документов);
* ``unique``     — number of distinct ``content_hash`` values (уникальные);
* ``duplicates`` — ids of the dropped documents, i.e. every non-first member of
  a hash group, in input order (``len == total - unique``) (дубликаты);
* ``by_hash``    — ``content_hash → [doc ids…]`` in first-seen order (по хэшу).

:meth:`DedupReport.duplicate_pairs` expands the groups into ``(kept, dropped)``
id pairs — one row per dropped document — the shape a merge/audit log wants.

Pure Python — stdlib only, no LLM, no I/O.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

#: One parsed document as seen by the report: ``{id, content_hash, ...}`` (§5.12).
Doc = Mapping[str, object]

# --- field keys read off each document (ключи входного документа) -------------
KEY_ID = "id"  # идентификатор документа
KEY_HASH = "content_hash"  # sha256 контента (§5.4)


@dataclass(frozen=True)
class DedupReport:
    """Source-dedup summary over a batch of documents (§5.12).

    Fields
    ------
    total
        Number of documents in the batch (всего документов).
    unique
        Number of distinct ``content_hash`` values (уникальные хэши).
    duplicates
        Ids of the dropped documents — every non-first member of a hash group,
        in input order; ``len(duplicates) == total - unique`` (дубликаты).
    by_hash
        ``content_hash → [doc ids…]`` in first-seen order; a group of length one
        is a document with no duplicate (карта по хэшу).
    """

    total: int
    unique: int
    duplicates: list[str] = field(default_factory=list)
    by_hash: dict[str, list[str]] = field(default_factory=dict)

    @property
    def has_duplicates(self) -> bool:
        """True when at least one document was dropped as a duplicate."""
        return len(self.duplicates) > 0

    def duplicate_pairs(self) -> list[tuple[str, str]]:
        """Expand hash groups into ``(kept, dropped)`` id pairs (§5.12).

        The first id per hash is the kept original; each later id yields one
        ``(kept, dropped)`` row. Groups without duplicates contribute nothing,
        so the result has exactly :attr:`duplicates` length, in input order.
        """
        pairs: list[tuple[str, str]] = []
        for ids in self.by_hash.values():
            kept = ids[0]
            for dropped in ids[1:]:
                pairs.append((kept, dropped))
        return pairs

    def as_dict(self) -> dict[str, object]:
        """Full structured view (all fields, JSON-friendly, deep-copied)."""
        return {
            "total": self.total,
            "unique": self.unique,
            "duplicates": list(self.duplicates),
            "by_hash": {h: list(ids) for h, ids in self.by_hash.items()},
        }


def build_dedup_report(docs: Iterable[Doc]) -> DedupReport:
    """Group documents by ``content_hash`` into a :class:`DedupReport` (§5.12).

    Each document must expose an ``id`` and a ``content_hash``. Documents are
    grouped by hash in first-seen order; within a group the first document is
    kept and the rest are recorded as dropped duplicates. An empty input yields
    an all-zero report (``total == unique == 0``, empty collections).
    """
    by_hash: dict[str, list[str]] = {}
    duplicates: list[str] = []
    total = 0
    for doc in docs:
        total += 1
        doc_id = str(doc[KEY_ID])
        content_hash = str(doc[KEY_HASH])
        group = by_hash.get(content_hash)
        if group is None:
            by_hash[content_hash] = [doc_id]
        else:
            group.append(doc_id)
            duplicates.append(doc_id)
    return DedupReport(
        total=total,
        unique=len(by_hash),
        duplicates=duplicates,
        by_hash=by_hash,
    )
