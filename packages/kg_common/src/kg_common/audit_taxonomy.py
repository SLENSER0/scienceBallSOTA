"""Audit action / target-type taxonomy — таксономия аудита (§10.8).

Section 10.8 extends the ``CurationEvent`` vocabulary of §12.3 with the
API-side actions and targets that the service layer must also audit. A
curation decision («принять / отклонить / исправить …») is only *part* of
the trail: uploading a source, kicking off an ingest job and opening a
review are privileged too and share the same audit spine.

This module is the single source of truth for *which* verbs and *which*
object kinds are auditable, so callers never hard-code magic strings:

* Curation verbs (§12.3): ``accept`` / ``reject`` / ``correct`` / ``merge`` /
  ``split`` / ``alias_add`` / ``schema_change``.
* API verbs (§10.8): ``upload`` / ``ingest`` / ``review``.
* Curation targets (§12.3): ``node`` / ``edge`` / ``evidence`` / ``schema``.
* API targets (§10.8): ``source`` / ``document`` / ``job``.

Everything is deterministic and side-effect free — the constants are
:class:`frozenset` instances so the vocabulary cannot be mutated at runtime
(«словарь аудита неизменяем»).

Public API:

* :data:`CURATION_ACTIONS` / :data:`API_ACTIONS` / :data:`AUDIT_ACTIONS`.
* :data:`CURATION_TARGETS` / :data:`API_TARGETS` / :data:`AUDIT_TARGET_TYPES`.
* :class:`AuditVocabulary`  — frozen snapshot with :meth:`AuditVocabulary.as_dict`.
* :func:`is_valid_action`   — is *a* an auditable verb?
* :func:`is_valid_target`   — is *t* an auditable target kind?
* :func:`validate_event`    — are both action and target valid?
* :func:`normalize_action`  — lowercase/strip a verb, raising on unknowns.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "API_ACTIONS",
    "API_TARGETS",
    "AUDIT_ACTIONS",
    "AUDIT_TARGET_TYPES",
    "CURATION_ACTIONS",
    "CURATION_TARGETS",
    "AuditVocabulary",
    "is_valid_action",
    "is_valid_target",
    "normalize_action",
    "validate_event",
]

# Curation verbs — глаголы кураторства (§12.3, CurationEvent).
CURATION_ACTIONS: frozenset[str] = frozenset(
    {"accept", "reject", "correct", "merge", "split", "alias_add", "schema_change"}
)

# API verbs — глаголы API (§10.8).
API_ACTIONS: frozenset[str] = frozenset({"upload", "ingest", "review"})

# Full auditable-action vocabulary — полный словарь действий (§10.8).
AUDIT_ACTIONS: frozenset[str] = CURATION_ACTIONS | API_ACTIONS

# Curation targets — цели кураторства (§12.3).
CURATION_TARGETS: frozenset[str] = frozenset({"node", "edge", "evidence", "schema"})

# API targets — цели API (§10.8).
API_TARGETS: frozenset[str] = frozenset({"source", "document", "job"})

# Full auditable-target vocabulary — полный словарь целей (§10.8).
AUDIT_TARGET_TYPES: frozenset[str] = CURATION_TARGETS | API_TARGETS


@dataclass(frozen=True)
class AuditVocabulary:
    """An immutable snapshot of the audit vocabulary — словарь аудита (§10.8).

    Bundles the auditable *actions* and *target_types* into one frozen record so
    the whole taxonomy can be serialized (e.g. exposed on a ``/meta`` endpoint or
    embedded in an OpenAPI schema) without callers touching module globals.
    Defaults mirror :data:`AUDIT_ACTIONS` and :data:`AUDIT_TARGET_TYPES`.
    """

    actions: frozenset[str] = AUDIT_ACTIONS
    target_types: frozenset[str] = AUDIT_TARGET_TYPES

    def as_dict(self) -> dict[str, list[str]]:
        """JSON-friendly view — ``{actions, target_types}`` sorted (§10.8).

        Each set is rendered as a *sorted* list so the serialized form is stable
        across runs (frozenset iteration order is not guaranteed).
        """
        return {
            "actions": sorted(self.actions),
            "target_types": sorted(self.target_types),
        }


def is_valid_action(a: str) -> bool:
    """Is *a* an auditable verb? — допустимое действие? (§10.8).

    Membership test against :data:`AUDIT_ACTIONS`; the input is compared as-is
    (no normalization) — use :func:`normalize_action` first for loose input.
    """
    return a in AUDIT_ACTIONS


def is_valid_target(t: str) -> bool:
    """Is *t* an auditable target kind? — допустимая цель? (§10.8).

    Membership test against :data:`AUDIT_TARGET_TYPES`.
    """
    return t in AUDIT_TARGET_TYPES


def validate_event(action: str, target_type: str) -> bool:
    """Are both *action* and *target_type* valid? — проверка события (§10.8).

    Returns ``True`` only when the verb is in :data:`AUDIT_ACTIONS` *and* the
    target kind is in :data:`AUDIT_TARGET_TYPES`; either miss yields ``False``.
    """
    return is_valid_action(action) and is_valid_target(target_type)


def normalize_action(a: str) -> str:
    """Canonicalize a verb — нормализация действия (§10.8).

    Strips surrounding whitespace and lowercases *a*, then verifies the result
    is a known verb. Raises :class:`ValueError` for anything not in
    :data:`AUDIT_ACTIONS` («неизвестное действие аудита»).
    """
    canonical = a.strip().lower()
    if canonical not in AUDIT_ACTIONS:
        raise ValueError(f"unknown audit action: {a!r}")
    return canonical
