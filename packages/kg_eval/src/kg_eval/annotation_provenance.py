"""Annotation provenance guard для золотых данных eval (§23.26).

Golden eval data must carry *annotation provenance* so quality is auditable, not
assumed. This module models that metadata and validates it against acceptance
thresholds — the protocol half of §23.26 (annotation protocol and quality control:
версия схемы, ссылка на гайдлайны, IAA-каппа, доля двойной разметки).

The frozen :class:`AnnotationProvenance` record captures four facts:

* ``schema_version`` — schema/version the golden set was annotated against;
* ``guidelines_ref`` — reference to the written annotation guidelines;
* ``iaa_kappa`` — inter-annotator agreement (Cohen/Fleiss kappa);
* ``double_annotated_fraction`` — fraction of items labelled by ≥2 annotators.

:func:`validate` returns ``(ok, reasons)`` where ``reasons`` is a *sorted* tuple of
short machine codes for every failed check, so callers get deterministic output.
Thresholds are inclusive lower bounds (``>=``): kappa exactly at ``min_kappa`` passes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class AnnotationProvenance:
    """Provenance of a golden annotation set (§23.26).

    ``iaa_kappa`` and ``double_annotated_fraction`` are quality signals in
    ``[-1, 1]`` / ``[0, 1]`` respectively; ``schema_version`` and ``guidelines_ref``
    are free-form references that must be non-empty to count as present.
    """

    schema_version: str
    guidelines_ref: str
    iaa_kappa: float
    double_annotated_fraction: float

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "guidelines_ref": self.guidelines_ref,
            "iaa_kappa": self.iaa_kappa,
            "double_annotated_fraction": self.double_annotated_fraction,
        }


def from_meta(meta: Mapping[str, object]) -> AnnotationProvenance:
    """Build :class:`AnnotationProvenance` from a raw metadata mapping.

    Missing string keys become ``""`` and missing numeric keys become ``0.0`` so a
    partial ``meta`` still yields a record (which :func:`validate` will then reject).
    """
    return AnnotationProvenance(
        schema_version=str(meta.get("schema_version") or ""),
        guidelines_ref=str(meta.get("guidelines_ref") or ""),
        iaa_kappa=float(meta.get("iaa_kappa") or 0.0),
        double_annotated_fraction=float(meta.get("double_annotated_fraction") or 0.0),
    )


def validate(
    meta: Mapping[str, object],
    *,
    min_kappa: float = 0.6,
    min_double: float = 0.2,
) -> tuple[bool, tuple[str, ...]]:
    """Validate annotation provenance ``meta`` against acceptance thresholds.

    Returns ``(ok, reasons)`` where ``reasons`` is a sorted tuple of failure codes:

    * ``"schema_version"`` — ``schema_version`` missing or empty;
    * ``"guidelines"`` — ``guidelines_ref`` missing or empty;
    * ``"iaa_kappa"`` — ``iaa_kappa`` below ``min_kappa`` (inclusive bound);
    * ``"double_annotation"`` — ``double_annotated_fraction`` below ``min_double``.

    ``ok`` is ``True`` iff ``reasons`` is empty. Thresholds are ``>=`` comparisons, so
    a value exactly equal to the minimum passes.
    """
    prov = from_meta(meta)
    reasons: list[str] = []
    if not prov.schema_version:
        reasons.append("schema_version")
    if not prov.guidelines_ref:
        reasons.append("guidelines")
    if prov.iaa_kappa < min_kappa:
        reasons.append("iaa_kappa")
    if prov.double_annotated_fraction < min_double:
        reasons.append("double_annotation")
    reasons.sort()
    return (not reasons, tuple(reasons))
