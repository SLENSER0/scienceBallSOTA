"""Full ``kg_common.units`` engine glue → normalization provenance (§7.9).

The ingestion path historically canonicalized values through the *reduced*
normalizer (:func:`kg_extractors.measurement_normalizer.normalize_measurement`),
which records ``value_normalized`` / ``normalized_unit`` / curator flags but
never the two provenance fields §7.9 wants surfaced on a citation:

* ``normalization_method`` — how the canonical value was obtained
  (``direct`` | ``converted`` | ``rule`` | ``manual``, §7.5); and
* ``unit_registry_version`` — the content-hash of the unit catalogue that did
  the conversion (§7.11), so a reader can tell *which* registry produced it.

Both derivers already exist in ``kg_common.units`` but were never wired
together. This module composes the **full engine** — the reduced normalizer for
value/unit/flags, plus :func:`classify_normalization_method` for the method and
:func:`registry_version` / :func:`dimension_of` for the catalogue provenance —
into one :class:`UnitProvenance` the Evidence Inspector can render.

Pure compute, no I/O: the router feeds it either a live ``:Measurement`` node or
an ad-hoc ``value_raw``/``unit`` triplet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from kg_common.units.normalization_method import classify_normalization_method
from kg_common.units.policy import PROPERTY_UNIT_POLICY
from kg_common.units.registry import (
    dimension_of,
    registry_version,
    resolve_alias,
)
from kg_extractors.measurement_normalizer import normalize_measurement


def _policy_canonical(property_id: str | None) -> str | None:
    """Canonical target unit the property's policy expects (§7.2), or ``None``."""
    if property_id is None:
        return None
    policy = PROPERTY_UNIT_POLICY.get(property_id)
    if policy is None:
        return None
    canonical = policy.get("canonical_unit")
    return canonical if isinstance(canonical, str) and canonical else None


def _dimension(unit: str | None) -> str | None:
    """Physical dimension of *unit* (§7.11); ``None`` for unregistered units.

    Non-pint scales such as Vickers ``HV`` are legitimately outside the registry
    — that is not an error here, just an absent dimension.
    """
    if unit is None:
        return None
    try:
        return dimension_of(unit)
    except ValueError:
        return None


@dataclass(frozen=True)
class UnitProvenance:
    """Full normalization provenance for one measurement (§7.9).

    Bundles the reduced normalizer's numeric result with the two §7.9 provenance
    fields (``normalization_method`` + ``unit_registry_version``) and enough
    context (dimension, canonical target, method reason, flags) for the Evidence
    Inspector to explain *how* the shown value was obtained.
    """

    property_id: str | None
    value_raw: object
    value: float | None
    unit: str | None
    value_normalized: float | None
    normalized_unit: str | None
    #: §7.5 — direct | converted | rule | manual.
    normalization_method: str
    method_reason: str
    #: §7.11 — content hash of the unit catalogue ("ur1:<hex>").
    unit_registry_version: str
    #: physical dimension of the canonical unit (pressure/length/…); None if the
    #: unit is outside the registry (e.g. Vickers HV).
    dimension: str | None
    #: canonical unit the policy expects for this property (§7.2), if known.
    policy_canonical_unit: str | None
    #: canonical spelling the registry resolves the raw unit to (§7.11), if known.
    registry_canonical_unit: str | None
    in_range: bool
    review_needed: bool
    flags: list[str] = field(default_factory=list)
    normalized_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_provenance(
    value: object,
    unit: str | None,
    *,
    property_id: str | None = None,
    manual: bool = False,
) -> UnitProvenance:
    """Run the full unit engine over one measurement and record its provenance.

    Steps (§7.9): canonicalize value + unit and gate it through the reduced
    normalizer (reused, not reimplemented); then layer on the method label
    (:func:`classify_normalization_method`), the catalogue version
    (:func:`registry_version`) and the canonical dimension.

    ``manual=True`` marks a curator-fixed value so the method is pinned to
    ``manual`` (§9.7 «never overwrite reviewed fields»), regardless of units.
    """
    nm = normalize_measurement(value, unit, property_id=property_id)

    raw_unit = nm.unit
    canonical_unit = nm.normalized_unit
    unit_missing = "missing_unit" in nm.flags or raw_unit is None

    decision = classify_normalization_method(
        raw_unit,
        canonical_unit,
        manual=manual,
        assumed=unit_missing,
        rule_based=False,
    )

    return UnitProvenance(
        property_id=property_id,
        value_raw=nm.value_raw,
        value=nm.value,
        unit=raw_unit,
        value_normalized=nm.value_normalized,
        normalized_unit=canonical_unit,
        normalization_method=decision.method,
        method_reason=decision.reason,
        unit_registry_version=registry_version(),
        dimension=_dimension(canonical_unit),
        policy_canonical_unit=_policy_canonical(property_id),
        registry_canonical_unit=resolve_alias(raw_unit),
        in_range=nm.in_range,
        review_needed=nm.review_needed,
        flags=list(nm.flags),
        normalized_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


def provenance_from_node(node: dict[str, Any]) -> UnitProvenance:
    """Build provenance from a stored ``:Measurement`` node (§7.9).

    Reads whichever of ``value_raw`` / ``value`` / ``value_normalized`` and
    ``unit`` / ``normalized_unit`` the node carries (ingested nodes vary), plus
    ``property_id``, and re-derives the full provenance. A node already flagged
    ``normalization_method="manual"`` keeps that label (curator override).
    """
    raw_value = node.get("value_raw")
    if raw_value is None:
        raw_value = node.get("value")
    if raw_value is None:
        raw_value = node.get("value_normalized")

    unit = node.get("unit") or node.get("normalized_unit")
    property_id = node.get("property_id")
    manual = str(node.get("normalization_method") or "").strip().lower() == "manual"

    return build_provenance(raw_value, unit, property_id=property_id, manual=manual)
