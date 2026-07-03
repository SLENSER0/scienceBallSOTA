"""Action ``manual_evidence`` — ручная фабрикация верифицированного Evidence (§16.6).

When a curator manually asserts that some free-text supports a target node, the
system must **fabricate** an :class:`Evidence`-like record that is already
*verified* (``source_type=='manual'``, ``extractor=='manual'``, human-reviewed)
together with a ``SUPPORTS`` edge that links the new evidence to the target.

Because the evidence is authored by a human — не извлечено моделью — it bypasses
the usual extraction pipeline: it is born ``verified`` with
``review_status=='accepted'`` and carries the acting curator as ``reviewed_by``.

Public API:

* :class:`ManualEvidence` — frozen ``(evidence, edge)`` pair with :meth:`~ManualEvidence.as_dict`.
* :func:`build_manual_evidence` — fabricate the evidence dict and its SUPPORTS edge.
* :func:`validate_inputs`       — collect input errors before building.

Pure Python, no I/O.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# Тип связи: manual evidence всегда «поддерживает» целевой узел (§16.6).
SUPPORTS_REL_TYPE = "SUPPORTS"

# Префикс детерминированного идентификатора сфабрикованного evidence (§16.6).
MANUAL_ID_PREFIX = "ev:manual:"

# Константы ручного источника — born verified, human-reviewed (§16.6).
MANUAL_SOURCE_TYPE = "manual"
MANUAL_EXTRACTOR = "manual"
MANUAL_REVIEW_STATUS = "accepted"


@dataclass(frozen=True)
class ManualEvidence:
    """Пара «evidence + SUPPORTS edge» — итог действия ``manual_evidence`` (§16.6).

    ``evidence`` — сфабрикованный узел Evidence (``source_type=='manual'``, verified).
    ``edge``     — ребро ``{src, rel_type: 'SUPPORTS', dst}`` из evidence в цель.
    """

    evidence: dict[str, object]
    edge: dict[str, str]

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view nesting evidence and edge — строка результата (§16.6)."""
        return {
            "evidence": self.evidence,
            "edge": self.edge,
        }


def _default_evidence_id(target_id: str, text: str) -> str:
    """Deterministic ``'ev:manual:'`` id from ``target_id + text`` — sha1[:12] (§16.6)."""
    digest = hashlib.sha1((target_id + text).encode("utf-8")).hexdigest()
    return f"{MANUAL_ID_PREFIX}{digest[:12]}"


def validate_inputs(target_id: str, text: str) -> list[str]:
    """Collect input errors for a manual-evidence request — пустые поля (§16.6).

    Returns a list of human-readable errors (empty when valid): ``target_id`` must
    be non-empty and *text* must not be blank (whitespace-only counts as blank).
    """
    errors: list[str] = []
    if not target_id:
        errors.append("target_id must not be empty")
    if not text or not text.strip():
        errors.append("text must not be blank")
    return errors


def build_manual_evidence(
    target_id: str,
    text: str,
    actor: str,
    now: str,
    evidence_id: str | None = None,
) -> ManualEvidence:
    """Fabricate a verified manual Evidence plus a SUPPORTS edge to *target_id* (§16.6).

    The produced evidence dict is born *verified*: ``source_type=='manual'``,
    ``extractor=='manual'``, ``verified is True``, ``review_status=='accepted'``,
    ``reviewed_by==actor`` and ``reviewed_at==now``, carrying the supplied *text*.

    When *evidence_id* is omitted a deterministic ``'ev:manual:'``-prefixed id is
    derived from ``sha1(target_id + text)[:12]`` — стабильный между вызовами; an
    explicit *evidence_id* is used verbatim.

    The returned :class:`ManualEvidence` pairs the evidence with an edge
    ``{src: evidence.id, rel_type: 'SUPPORTS', dst: target_id}``.
    """
    ev_id = evidence_id if evidence_id is not None else _default_evidence_id(target_id, text)
    evidence: dict[str, object] = {
        "id": ev_id,
        "source_type": MANUAL_SOURCE_TYPE,
        "extractor": MANUAL_EXTRACTOR,
        "verified": True,
        "review_status": MANUAL_REVIEW_STATUS,
        "reviewed_by": actor,
        "reviewed_at": now,
        "text": text,
    }
    edge: dict[str, str] = {
        "src": ev_id,
        "rel_type": SUPPORTS_REL_TYPE,
        "dst": target_id,
    }
    return ManualEvidence(evidence=evidence, edge=edge)


__all__ = [
    "MANUAL_EXTRACTOR",
    "MANUAL_ID_PREFIX",
    "MANUAL_REVIEW_STATUS",
    "MANUAL_SOURCE_TYPE",
    "SUPPORTS_REL_TYPE",
    "ManualEvidence",
    "build_manual_evidence",
    "validate_inputs",
]
