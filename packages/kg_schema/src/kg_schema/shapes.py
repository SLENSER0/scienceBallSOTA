"""Lightweight SHACL-style shape validation for FAIR export (§24.19).

Validates plain node ``dict``s against the domain ontology (§8.1) *without*
requiring ``rdflib``/``pyshacl`` — the rules are ordinary Python data, so they
run anywhere (ingest, CI, FAIR/standards export). Two things are checked:

* **required / recommended fields** — presence of the fields a node label must
  (violation) or should (warning) carry;
* **controlled vocabularies** (``one_of``) — e.g. ``evidence_strength`` /
  ``review_status`` must be a permissible enum value;
* **evidence-first invariant** (§3.6/§3.7) — factual nodes (Measurement/Claim/
  Finding/Recommendation/KnowledgeClaim/Contradiction) and Evidence MUST carry
  the provenance fields ``extractor_run_id`` and ``created_at``. A missing
  provenance field is reported as a distinct *evidence-first* violation.

Field names / vocab values are sourced from :mod:`kg_schema.labels` and
:mod:`kg_schema.enums` so the shapes never drift from the ontology.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from kg_schema.enums import EvidenceStrength, ReviewStatus, SourceType
from kg_schema.labels import FACTUAL_LABELS, NodeLabel

# Provenance fields that make a fact traceable (§3.6/§3.7 evidence-first).
PROVENANCE_FIELDS: tuple[str, ...] = ("extractor_run_id", "created_at")

# Severity levels, ordered by decreasing importance.
SEVERITY_VIOLATION = "violation"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

_REVIEW_STATUS = [s.value for s in ReviewStatus]
_EVIDENCE_STRENGTH = [s.value for s in EvidenceStrength]
_SOURCE_TYPE = [s.value for s in SourceType]

# Labels that carry the evidence-first provenance obligation.
_PROVENANCE_LABELS: frozenset[str] = frozenset(FACTUAL_LABELS) | {NodeLabel.EVIDENCE.value}


def _build_shapes() -> dict[str, dict[str, Any]]:
    """Construct the SHAPES catalog from the ontology labels/enums (§24.19)."""
    shapes: dict[str, dict[str, Any]] = {}
    for label in sorted(FACTUAL_LABELS):
        shapes[str(label)] = {
            "required": ["id", "name", "extractor_run_id", "created_at"],
            "recommended": ["confidence", "review_status", "evidence_strength"],
            "one_of": {
                "review_status": list(_REVIEW_STATUS),
                "evidence_strength": list(_EVIDENCE_STRENGTH),
            },
        }
    # Measurement additionally recommends value/unit fields (§8.1).
    shapes[NodeLabel.MEASUREMENT.value]["recommended"] = [
        "confidence",
        "review_status",
        "evidence_strength",
        "unit",
        "normalized_unit",
        "value_normalized",
    ]
    # Evidence: source-span invariant — must point at a document span (§3.3/§8.3).
    shapes[NodeLabel.EVIDENCE.value] = {
        "required": ["id", "doc_id", "text", "extractor_run_id", "created_at"],
        "recommended": ["evidence_strength", "source_type", "page", "review_status"],
        "one_of": {
            "evidence_strength": list(_EVIDENCE_STRENGTH),
            "review_status": list(_REVIEW_STATUS),
            "source_type": list(_SOURCE_TYPE),
        },
    }
    return shapes


# Public shapes catalog: label -> {required, recommended, one_of}.
SHAPES: dict[str, dict[str, Any]] = _build_shapes()


@dataclass(frozen=True)
class ShapeViolation:
    """A single conformance issue found on a node (§24.19)."""

    field: str
    severity: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "severity": self.severity, "message": self.message}


@dataclass
class ValidationResult:
    """Result of validating one node against its NodeShape."""

    label: str | None
    conforms: bool = True
    violations: list[ShapeViolation] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "conforms": self.conforms,
            "violations": [v.as_dict() for v in self.violations],
        }


@dataclass
class ValidationReport:
    """Aggregate report over many nodes (§24.19)."""

    total: int
    conforming: int
    by_severity: dict[str, int]
    nonconforming_by_label: dict[str, int]
    results: list[ValidationResult]

    @property
    def nonconforming(self) -> int:
        return self.total - self.conforming

    @property
    def conforms(self) -> bool:
        return self.conforming == self.total

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "conforming": self.conforming,
            "nonconforming": self.nonconforming,
            "conforms": self.conforms,
            "by_severity": dict(self.by_severity),
            "nonconforming_by_label": dict(self.nonconforming_by_label),
            "results": [r.as_dict() for r in self.results],
        }


def _node_label(node: Mapping[str, Any]) -> str | None:
    """Return the node's single label, tolerating a ``labels`` list."""
    label = node.get("label")
    if label is None:
        labels = node.get("labels") or []
        label = labels[0] if labels else None
    return None if label is None else str(label)


def _is_missing(node: Mapping[str, Any], name: str) -> bool:
    """A field is missing if absent, ``None``, or a blank string."""
    if name not in node:
        return True
    value = node[name]
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _validate(node: Mapping[str, Any]) -> ValidationResult:
    label = _node_label(node)
    result = ValidationResult(label=label)
    shape = SHAPES.get(label) if label is not None else None
    if shape is None:
        # Unknown / unmodelled label — graceful skip, still conforms.
        result.violations.append(
            ShapeViolation(
                "label",
                SEVERITY_INFO,
                f"no NodeShape defined for label {label!r} — validation skipped",
            )
        )
        return result

    is_provenance_label = label in _PROVENANCE_LABELS

    for name in shape.get("required", []):
        if not _is_missing(node, name):
            continue
        if name in PROVENANCE_FIELDS and is_provenance_label:
            result.violations.append(
                ShapeViolation(
                    name,
                    SEVERITY_VIOLATION,
                    f"evidence-first invariant (§3.6/§3.7): {label} must carry "
                    f"provenance field {name!r}",
                )
            )
        else:
            result.violations.append(
                ShapeViolation(
                    name,
                    SEVERITY_VIOLATION,
                    f"required field {name!r} missing for {label}",
                )
            )

    for name in shape.get("recommended", []):
        if _is_missing(node, name):
            result.violations.append(
                ShapeViolation(
                    name,
                    SEVERITY_WARNING,
                    f"recommended field {name!r} absent for {label}",
                )
            )

    for name, allowed in shape.get("one_of", {}).items():
        if _is_missing(node, name):
            continue
        value = str(node[name])
        if value not in allowed:
            result.violations.append(
                ShapeViolation(
                    name,
                    SEVERITY_VIOLATION,
                    f"field {name!r} value {value!r} not in allowed set for {label}",
                )
            )

    result.conforms = not any(v.severity == SEVERITY_VIOLATION for v in result.violations)
    return result


def validate_node(node: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one node dict → ``{conforms: bool, violations: [...]}`` (§24.19).

    ``violations`` items are ``{field, severity, message}``. Warnings/info notes
    do not affect ``conforms`` — only ``severity == "violation"`` does.
    """
    return _validate(node).as_dict()


def validate_nodes(nodes: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate many nodes → aggregate report with counts (§24.19)."""
    results = [_validate(n) for n in nodes]
    by_severity: dict[str, int] = {
        SEVERITY_VIOLATION: 0,
        SEVERITY_WARNING: 0,
        SEVERITY_INFO: 0,
    }
    nonconforming_by_label: dict[str, int] = {}
    conforming = 0
    for res in results:
        if res.conforms:
            conforming += 1
        else:
            key = str(res.label)
            nonconforming_by_label[key] = nonconforming_by_label.get(key, 0) + 1
        for v in res.violations:
            by_severity[v.severity] = by_severity.get(v.severity, 0) + 1
    report = ValidationReport(
        total=len(results),
        conforming=conforming,
        by_severity=by_severity,
        nonconforming_by_label=nonconforming_by_label,
        results=results,
    )
    return report.as_dict()


def known_labels() -> frozenset[str]:
    """Labels that have a NodeShape defined (§24.19)."""
    return frozenset(SHAPES)


__all__ = [
    "PROVENANCE_FIELDS",
    "SHAPES",
    "ShapeViolation",
    "ValidationReport",
    "ValidationResult",
    "known_labels",
    "validate_node",
    "validate_nodes",
]
