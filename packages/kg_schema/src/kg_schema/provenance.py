"""Provenance-completeness validation (§3.7 — every factual node carries provenance).

Каждый фактический узел (*factual node* — Measurement / Claim / Finding /
Recommendation / KnowledgeClaim / Contradiction) MUST be traceable back to the
extractor run that produced it and to the schema version in force at that time.
This module checks that obligation on plain node ``dict``s — no graph store, no
Pydantic, pure Python — so it runs anywhere (ingest, CI, curation, FAIR export).

Обязательные поля происхождения (*required provenance fields*, §3.7):

* ``extractor_run_id`` — the :ExtractorRun that emitted the node (§8.2);
* ``schema_version``   — schema version at extraction time (§3.15 / §23.4);
* ``created_at``       — creation timestamp.

Non-factual nodes (Chunk, Document, Section, …) carry no such obligation, so
they are always reported ``complete`` with an empty ``missing`` list.

Complementary signals surfaced (but *not* required for completeness):

* ``review_status`` / ``confidence`` — curation state (§3.8);
* evidence link — the caller may set a ``_has_evidence`` bool on the node dict
  (from an EVIDENCED_BY / SUPPORTED_BY edge lookup, §3.6) which is echoed back
  as ``has_evidence_link``.

Labels are sourced from :mod:`kg_schema.labels` so this never drifts from the
ontology (§8.1).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from kg_schema.labels import FACTUAL_LABELS

# Provenance fields a factual node MUST carry to be traceable (§3.7).
REQUIRED_PROVENANCE: tuple[str, ...] = ("extractor_run_id", "schema_version", "created_at")

# Curation signals we *note* but do not require (§3.8).
_CURATION_FIELDS: tuple[str, ...] = ("review_status", "confidence")


@dataclass(frozen=True)
class ProvenanceCheck:
    """Outcome of validating one node's provenance completeness (§3.7).

    Attributes
    ----------
    complete:
        For a factual node — every field in :data:`REQUIRED_PROVENANCE` present.
        For a non-factual node — always ``True`` (no obligation).
    missing:
        Required provenance fields absent on a factual node (empty otherwise).
    is_factual:
        Whether the node's label is in :data:`~kg_schema.labels.FACTUAL_LABELS`.
    has_evidence_link:
        Echo of the caller-supplied ``_has_evidence`` flag (§3.6 evidence-first).
    has_review_status:
        Whether ``review_status`` is present (curation signal, §3.8).
    has_confidence:
        Whether ``confidence`` is present (curation signal, §3.8).
    label:
        The node's resolved label (``None`` if unlabelled).
    """

    complete: bool
    missing: list[str] = field(default_factory=list)
    is_factual: bool = False
    has_evidence_link: bool = False
    has_review_status: bool = False
    has_confidence: bool = False
    label: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-friendly dict (§3.7)."""
        return {
            "complete": self.complete,
            "missing": list(self.missing),
            "is_factual": self.is_factual,
            "has_evidence_link": self.has_evidence_link,
            "has_review_status": self.has_review_status,
            "has_confidence": self.has_confidence,
            "label": self.label,
        }


def _node_label(node: Mapping[str, Any]) -> str | None:
    """Return the node's single label, tolerating a ``labels`` list (§8.1)."""
    label = node.get("label")
    if label is None:
        labels = node.get("labels") or []
        label = labels[0] if labels else None
    return None if label is None else str(label)


def _is_missing(node: Mapping[str, Any], name: str) -> bool:
    """A field is missing if absent, ``None``, or a blank/whitespace string."""
    if name not in node:
        return True
    value = node[name]
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def validate_provenance(node: Mapping[str, Any]) -> ProvenanceCheck:
    """Validate one node dict's provenance completeness (§3.7).

    Factual nodes (label in :data:`~kg_schema.labels.FACTUAL_LABELS`) must carry
    every field in :data:`REQUIRED_PROVENANCE`; any absent field is reported in
    ``missing`` and drops ``complete`` to ``False``. Non-factual nodes carry no
    obligation and are always ``complete`` with an empty ``missing`` list.
    """
    label = _node_label(node)
    is_factual = label in FACTUAL_LABELS
    missing = [f for f in REQUIRED_PROVENANCE if _is_missing(node, f)] if is_factual else []
    return ProvenanceCheck(
        complete=not missing,
        missing=missing,
        is_factual=is_factual,
        has_evidence_link=bool(node.get("_has_evidence", False)),
        has_review_status=not _is_missing(node, "review_status"),
        has_confidence=not _is_missing(node, "confidence"),
        label=label,
    )


def provenance_report(nodes: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate provenance completeness over many nodes (§3.7).

    Returns ``{total, complete, incomplete, by_missing_field}`` where
    ``by_missing_field`` counts, across all factual nodes, how often each
    required provenance field was absent.
    """
    total = 0
    complete = 0
    by_missing_field: dict[str, int] = {}
    for node in nodes:
        total += 1
        check = validate_provenance(node)
        if check.complete:
            complete += 1
        for name in check.missing:
            by_missing_field[name] = by_missing_field.get(name, 0) + 1
    return {
        "total": total,
        "complete": complete,
        "incomplete": total - complete,
        "by_missing_field": by_missing_field,
    }


__all__ = [
    "REQUIRED_PROVENANCE",
    "ProvenanceCheck",
    "provenance_report",
    "validate_provenance",
]
