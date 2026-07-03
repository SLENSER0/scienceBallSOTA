"""De-duplicate measurement extracts by identity, keeping the best (§6.18).

Downstream of the per-extractor emit and the §6.13 merge, the same measured
fact often arrives several times — a table cell and its prose restatement, the
rule extractor and the LLM agreeing, two chunks quoting one datum.  Each copy
carries its own confidence and its own evidence span id, but they describe **one
graph fact** and must collapse to one before they reach the store.

RU: дедупликация измерений — EN: measurement de-duplication.

Identity is the tuple ``(property, value, unit, subject)`` (§9.4): the measured
property, its numeric value, the unit it is expressed in, and the subject the
measurement is *about* (the material / sample).  Two extracts sharing that key
are the same fact; two differing in *any* component are kept apart — a value in
``MPa`` is not the value in ``GPa``, and 210 is not 211.

Collapsing rule (pure Python, no I/O, no LLM):

* **confidence** — the survivor keeps the **maximum** confidence of the group
  (the most trusted witness wins; a low-confidence duplicate never drags a
  high-confidence fact down);
* **evidence_ids** — the survivor's evidence spans are the **union** of every
  copy's ids, first-seen order preserved, so no provenance is dropped (the
  "no source span → no graph fact" invariant, §3.3/§3.6, is only reinforced).

Output preserves first-seen group order (stable, hand-checkable) and each item
is a frozen :class:`MergedMeasurement` with an :meth:`~MergedMeasurement.as_dict`
projection.  Input items are read-only mappings; the originals are never mutated.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

#: Decimals kept when normalizing values for keying — kills float noise so
#: ``210.0`` and ``210.0000001`` collapse (десятичные при округлении, §6.13).
_VALUE_DECIMALS = 6


@dataclass(frozen=True)
class MergedMeasurement:
    """One de-duplicated measurement — the survivor of an identity group (§6.18).

    Fields
    ------
    property
        The measured property, e.g. ``"yield_strength"`` (измеряемое свойство).
    value
        The numeric value, or ``None`` for a value-less mention (значение).
    unit
        The unit the value is expressed in, or ``None`` (единица измерения).
    subject
        What the measurement is about — material / sample id (субъект).
    confidence
        The **maximum** confidence across the merged group (уверенность).
    evidence_ids
        Union of every copy's evidence span ids, first-seen order preserved
        (идентификаторы доказательных фрагментов); a tuple to stay frozen.
    """

    property: str
    value: float | None
    unit: str | None
    subject: str
    confidence: float
    evidence_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Full structured view; ``evidence_ids`` as a list (все поля, §6.18)."""
        return {
            "property": self.property,
            "value": self.value,
            "unit": self.unit,
            "subject": self.subject,
            "confidence": self.confidence,
            "evidence_ids": list(self.evidence_ids),
        }


#: The identity key of a measurement: ``(property, value, unit, subject)``.
_Key = tuple[str, float | None, str | None, str]


def _norm_value(value: object) -> float | None:
    """Normalize a value for keying: ``None`` stays ``None``, else rounded float."""
    if value is None:
        return None
    return round(float(value), _VALUE_DECIMALS)


def _norm_unit(unit: object) -> str | None:
    """Normalize a unit for keying: ``None`` stays ``None``, else stripped str."""
    if unit is None:
        return None
    return str(unit).strip()


def _identity(item: Mapping[str, object]) -> _Key:
    """Build the ``(property, value, unit, subject)`` identity key (§9.4)."""
    return (
        str(item.get("property", "")).strip(),
        _norm_value(item.get("value")),
        _norm_unit(item.get("unit")),
        str(item.get("subject", "")).strip(),
    )


def _evidence_ids(item: Mapping[str, object]) -> list[str]:
    """Read an item's evidence ids as a list of strings (empty if absent)."""
    raw = item.get("evidence_ids")
    if raw is None:
        return []
    if isinstance(raw, str):  # a lone id, not an iterable of ids
        return [raw]
    if isinstance(raw, Iterable):
        return [str(x) for x in raw]
    return [str(raw)]


def _confidence(item: Mapping[str, object]) -> float:
    """Read an item's confidence (default ``0.0`` when absent/None)."""
    raw = item.get("confidence")
    return 0.0 if raw is None else float(raw)


def dedup_measurements(items: Iterable[Mapping[str, object]]) -> list[MergedMeasurement]:
    """Collapse duplicate measurements to one per identity, best-of (§6.18).

    Groups the *items* by their ``(property, value, unit, subject)`` identity
    (§9.4).  Within a group the survivor keeps the **maximum** ``confidence``
    and the **union** of every copy's ``evidence_ids`` (first-seen order, no
    duplicates).  Items differing in any identity component are kept separate —
    a differing value, unit or subject is a *different* fact.  Group order
    follows first appearance (stable, hand-checkable); an empty input yields an
    empty list.  Each *item* is a read-only mapping carrying ``property``,
    ``value``, ``unit``, ``subject``, ``confidence`` and ``evidence_ids``; the
    originals are never mutated.
    """
    order: list[_Key] = []
    confidences: dict[_Key, float] = {}
    evidence: dict[_Key, list[str]] = {}
    seen_ids: dict[_Key, set[str]] = {}

    for item in items:
        key = _identity(item)
        if key not in confidences:
            order.append(key)
            confidences[key] = _confidence(item)
            evidence[key] = []
            seen_ids[key] = set()
        else:
            confidences[key] = max(confidences[key], _confidence(item))
        for eid in _evidence_ids(item):
            if eid not in seen_ids[key]:
                seen_ids[key].add(eid)
                evidence[key].append(eid)

    out: list[MergedMeasurement] = []
    for prop, value, unit, subject in order:
        out.append(
            MergedMeasurement(
                property=prop,
                value=value,
                unit=unit,
                subject=subject,
                confidence=confidences[(prop, value, unit, subject)],
                evidence_ids=tuple(evidence[(prop, value, unit, subject)]),
            )
        )
    return out
