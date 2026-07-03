"""Lineage-diff between two provenance chains (§25.17).

Pure-python comparison of two *provenance chains* (цепочка происхождения) — the
audit trail behind an observation: the ``Evidence`` it is supported by and the
source documents (документы) those evidences come from. Given a ``before`` and an
``after`` chain, :func:`lineage_diff` reports which evidences and documents were
added or removed between the two, so a reviewer can see exactly how the support of
a fact shifted between two extraction runs (прогоны).

Диф происхождения: сравнение двух цепочек (эвиденс + документы), что добавилось /
удалилось.

A *provenance chain* is a plain dict carrying two collections keyed by
:data:`EVIDENCE_KEY` (``"evidence_ids"``) and :data:`DOC_KEY` (``"doc_ids"``); a
missing key is treated as empty, so the two chains need not share the same shape
and hand-made chains diff exactly the same way as ones read from a live lineage.
Duplicates within a chain collapse (set semantics) and every output tuple is
sorted for deterministic, hand-checkable output. The result is a frozen dataclass
exposing ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

# Provenance-chain dict keys (§25.17): the evidences and the source documents.
EVIDENCE_KEY = "evidence_ids"
DOC_KEY = "doc_ids"


def _as_str_set(values: Iterable[str] | None) -> set[str]:
    """Collapse a chain collection into a set of ids (``None`` → empty) (§25.17)."""
    if values is None:
        return set()
    return set(values)


@dataclass(frozen=True)
class LineageDiff:
    """Structured difference between two provenance chains (§25.17).

    - ``added_evidence`` — evidence ids present in *after* but not in *before*;
    - ``removed_evidence`` — evidence ids present in *before* but not in *after*;
    - ``added_docs`` — document ids present in *after* but not in *before*;
    - ``removed_docs`` — document ids present in *before* but not in *after*.

    All four tuples are sorted for deterministic output.
    """

    added_evidence: tuple[str, ...]
    removed_evidence: tuple[str, ...]
    added_docs: tuple[str, ...]
    removed_docs: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        """True when the two chains carry the same evidences and documents."""
        return not (
            self.added_evidence or self.removed_evidence or self.added_docs or self.removed_docs
        )

    def as_dict(self) -> dict:
        """JSON-serialisable view of the diff (§25.17)."""
        return {
            "added_evidence": list(self.added_evidence),
            "removed_evidence": list(self.removed_evidence),
            "added_docs": list(self.added_docs),
            "removed_docs": list(self.removed_docs),
            "is_empty": self.is_empty,
        }


def lineage_diff(before: dict, after: dict) -> LineageDiff:
    """Diff two provenance chains into a :class:`LineageDiff` (§25.17).

    ``before`` / ``after`` are chain dicts carrying :data:`EVIDENCE_KEY` and
    :data:`DOC_KEY` collections (missing keys treated as empty). Added ids are
    those in *after* and not *before*; removed ids are those in *before* and not
    *after*. Pure Python — no store required. Each output tuple is sorted.
    """
    before_ev = _as_str_set(before.get(EVIDENCE_KEY))
    after_ev = _as_str_set(after.get(EVIDENCE_KEY))
    before_docs = _as_str_set(before.get(DOC_KEY))
    after_docs = _as_str_set(after.get(DOC_KEY))

    return LineageDiff(
        added_evidence=tuple(sorted(after_ev - before_ev)),
        removed_evidence=tuple(sorted(before_ev - after_ev)),
        added_docs=tuple(sorted(after_docs - before_docs)),
        removed_docs=tuple(sorted(before_docs - after_docs)),
    )
