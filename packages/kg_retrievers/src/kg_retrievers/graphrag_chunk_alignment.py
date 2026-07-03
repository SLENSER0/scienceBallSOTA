"""GraphRAG chunk-config alignment check (§11.2).

GraphRAG re-chunks documents into *text units* (текстовые единицы) using the
``chunks.size`` / ``chunks.overlap`` knobs in its ``settings.yaml``. §11.2 requires
those knobs to match the §9.3 KG chunking strategy so that a GraphRAG text unit
lines up with a KG ``Chunk`` boundary — otherwise entity/claim offsets extracted by
GraphRAG cannot be traced back to the KG chunk they came from.

:mod:`kg_retrievers.graphrag_settings_validator` only checks that the *required
keys exist* in ``settings.yaml``; it never compares their values against the KG
config. This module fills that gap: :func:`check_alignment` reads ``size`` and
``overlap`` from each side and reports whether they agree (within ``tolerance``).

Проверка выравнивания (alignment check): both ``size`` and ``overlap`` must match
for the two configs to be aligned. A missing key on either side is treated as a
mismatch for that field — never a crash — so a half-written ``settings.yaml`` fails
the check loudly rather than silently passing.

Pure config comparison: no LLM, no graph store, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Field names compared across the two configs (порядок фиксирован).
_FIELDS: tuple[str, ...] = ("size", "overlap")

# Sentinel for a field absent from a config — distinct from any real int value.
_MISSING = object()


@dataclass(frozen=True)
class ChunkAlignment:
    """Result of comparing GraphRAG chunk config against the KG chunking config.

    Attributes:
        aligned: True iff *both* ``size`` and ``overlap`` match within tolerance.
        size_match: True iff the two ``size`` values differ by at most ``tolerance``.
        overlap_match: True iff the two ``overlap`` values differ by at most
            ``tolerance``.
        mismatches: names of the fields that differ (подмножество of ``_FIELDS``),
            in fixed field order.
    """

    aligned: bool
    size_match: bool
    overlap_match: bool
    mismatches: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict (tuple becomes a list)."""
        return {
            "aligned": self.aligned,
            "size_match": self.size_match,
            "overlap_match": self.overlap_match,
            "mismatches": list(self.mismatches),
        }


def _field_matches(
    graphrag_chunks: Mapping[str, Any],
    kg_chunking: Mapping[str, Any],
    field: str,
    tolerance: int,
) -> bool:
    """True iff ``field`` is present on both sides and within ``tolerance``.

    A missing key on either side (пропуск) counts as a mismatch, never a crash.
    """
    gr = graphrag_chunks.get(field, _MISSING)
    kg = kg_chunking.get(field, _MISSING)
    if gr is _MISSING or kg is _MISSING:
        return False
    return abs(int(gr) - int(kg)) <= tolerance


def check_alignment(
    graphrag_chunks: Mapping[str, Any],
    kg_chunking: Mapping[str, Any],
    tolerance: int = 0,
) -> ChunkAlignment:
    """Compare GraphRAG chunk config against KG chunking config (§11.2).

    Reads ``size`` and ``overlap`` from each mapping; each field matches iff both
    sides carry it and the absolute difference is at most ``tolerance``. ``mismatches``
    lists the differing field names in fixed order; ``aligned`` is True iff both match.

    Args:
        graphrag_chunks: GraphRAG ``settings.yaml`` ``chunks`` block (or equivalent).
        kg_chunking: §9.3 KG chunking config with ``size`` / ``overlap``.
        tolerance: max allowed absolute difference per field (default 0, exact match).

    Returns:
        A frozen :class:`ChunkAlignment`.
    """
    size_match = _field_matches(graphrag_chunks, kg_chunking, "size", tolerance)
    overlap_match = _field_matches(graphrag_chunks, kg_chunking, "overlap", tolerance)
    matched = {"size": size_match, "overlap": overlap_match}
    mismatches = tuple(f for f in _FIELDS if not matched[f])
    return ChunkAlignment(
        aligned=size_match and overlap_match,
        size_match=size_match,
        overlap_match=overlap_match,
        mismatches=mismatches,
    )
