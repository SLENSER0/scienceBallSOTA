"""Rule ``missing_critical_field`` — per-label critical field presence check (§16.5).

Each node label carries a small set of *critical* fields without which the node
is not usable downstream: a ``Measurement`` needs ``value`` / ``unit`` /
``property``; a ``ProcessingRegime`` needs ``temperature_c`` / ``time_h``; an
``Experiment`` needs ``material`` / ``property``. This module inspects a node
mapping and reports which critical fields are *absent* or present-but-empty
(``None`` or empty string), so the QA pass can flag under-specified nodes. A
node whose label is unknown, or whose critical fields are all populated, yields
no finding.

Правило ``missing_critical_field``: проверка обязательных полей по типу узла (§16.5).

Pure python — no dependency.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

# Per-label critical fields (§16.5). A node of this label is under-specified if
# any of these fields is absent, None, or an empty string.
CRITICAL_FIELDS: dict[str, list[str]] = {
    "Measurement": ["value", "unit", "property"],
    "ProcessingRegime": ["temperature_c", "time_h"],
    "Experiment": ["material", "property"],
}


@dataclass(frozen=True)
class MissingFieldFinding:
    """One node missing >=1 critical field for its label (§16.5)."""

    target_id: str
    label: str
    missing_fields: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "label": self.label,
            "missing_fields": list(self.missing_fields),
        }


def _is_missing(value: Any) -> bool:
    """True iff *value* is absent-like: ``None`` or an empty/blank string (§16.5)."""
    if value is None:
        return True
    return isinstance(value, str) and value.strip() == ""


def detect_missing(
    node: Mapping[str, Any],
    config: Mapping[str, list[str]] | None = None,
) -> MissingFieldFinding | None:
    """Return a finding of critical fields missing from *node*, or ``None`` (§16.5).

    The label is read from ``node['label']``. Critical fields come from *config*
    when given, else from :data:`CRITICAL_FIELDS`. A field counts as missing when
    the key is absent, or its value is ``None`` or an empty/blank string. Returns
    ``None`` when the label is unknown or nothing is missing.
    """
    fields_by_label = config if config is not None else CRITICAL_FIELDS
    label = node.get("label")
    if not isinstance(label, str):
        return None
    critical = fields_by_label.get(label)
    if not critical:
        return None
    missing = [f for f in critical if f not in node or _is_missing(node.get(f))]
    if not missing:
        return None
    target_id = str(node.get("id", ""))
    return MissingFieldFinding(target_id=target_id, label=label, missing_fields=missing)


def scan(
    nodes: Iterable[Mapping[str, Any]],
    config: Mapping[str, list[str]] | None = None,
) -> list[MissingFieldFinding]:
    """Scan *nodes*, returning one finding per under-specified node (§16.5)."""
    findings: list[MissingFieldFinding] = []
    for node in nodes:
        finding = detect_missing(node, config)
        if finding is not None:
            findings.append(finding)
    return findings
