"""Sample-node synthesis (§6.13).

A :class:`Sample` is the pivot node that ties one *specimen* together: it links
an ``Experiment`` to the ``Material`` it was made of, the ``ProcessingRegime``
it was put through, and the ``Measurement`` records taken on it (§8.1). The
extractors emit flat *records* — each a dict/obj carrying an ``experiment_id``,
``material_id``, ``regime_id`` and one or more measurement ids plus a
``doc_id`` — and this module folds records describing the *same* specimen into a
single Sample.

RU: синтез узла-образца — EN: sample-node synthesis.

Identity is **deterministic**: the ``sample_id`` is
``"sample:" + sha1(experiment_id|material_id|regime_id)[:12]``. The same
``(experiment, material, regime)`` triplet therefore always collapses to the
same node (idempotent re-ingest), while a different regime — a second heat
treatment on the same material — yields a distinct Sample. Records that omit a
material still synthesize a Sample (``material_id`` left ``None``) so the
specimen is not dropped; its ``OF_MATERIAL`` edge is simply not emitted.

:func:`sample_edges` emits the four declarative link specs — ``HAS_SAMPLE``
(``Experiment → Sample``), ``OF_MATERIAL`` (``Sample → Material``),
``UNDER_REGIME`` (``Sample → ProcessingRegime``) and ``HAS_MEASUREMENT``
(``Sample → Measurement``, one per measurement id) — in the same
``{source, target, type, from_label, to_label}`` shape used across §6.13.

Kuzu note: custom Sample props (``doc_id``, aggregated ``measurement_ids``) are
**not** queryable columns — a query RETURNs the base id column and reads the
rest via ``get_node()``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

# Node labels (§8.1) — string literals so this module stays pure-python.
_LABEL_EXPERIMENT = "Experiment"
_LABEL_SAMPLE = "Sample"
_LABEL_MATERIAL = "Material"
_LABEL_REGIME = "ProcessingRegime"
_LABEL_MEASUREMENT = "Measurement"

# Relation types linking a Sample to its neighbours (§8.1).
_REL_HAS_SAMPLE = "HAS_SAMPLE"
_REL_OF_MATERIAL = "OF_MATERIAL"
_REL_UNDER_REGIME = "UNDER_REGIME"
_REL_HAS_MEASUREMENT = "HAS_MEASUREMENT"

#: Hex characters kept from the sha1 digest (stable, hand-checkable ids).
_ID_HEX_LEN = 12


@dataclass(frozen=True)
class Sample:
    """A synthesized specimen node tying Experiment↔Material↔Regime↔Measurement.

    ``sample_id`` is deterministic (see :func:`make_sample_id`). ``material_id``
    is ``None`` when no material was linked. ``measurement_ids`` is an ordered,
    de-duplicated tuple of the measurement ids aggregated for this specimen.
    """

    sample_id: str
    experiment_id: str | None
    material_id: str | None
    regime_id: str | None
    measurement_ids: tuple[str, ...]
    doc_id: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "experiment_id": self.experiment_id,
            "material_id": self.material_id,
            "regime_id": self.regime_id,
            "measurement_ids": list(self.measurement_ids),
            "doc_id": self.doc_id,
        }


def _id_part(value: Any) -> str:
    """Render an id component for hashing: ``None`` -> ``""`` (stable key)."""
    return "" if value is None else str(value)


def make_sample_id(
    experiment_id: Any,
    material_id: Any,
    regime_id: Any,
) -> str:
    """Deterministic ``sample_id`` for a specimen triplet (§6.13).

    Returns ``"sample:" + sha1(experiment_id|material_id|regime_id)[:12]``. A
    missing component hashes as an empty string, so a material-less specimen
    still gets a stable id. Pure ``hashlib`` — the same triplet always maps to
    the same id (idempotent re-ingest).
    """
    key = f"{_id_part(experiment_id)}|{_id_part(material_id)}|{_id_part(regime_id)}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return f"sample:{digest[:_ID_HEX_LEN]}"


def _field(record: Any, name: str) -> Any:
    """Read ``name`` from a record that may be a ``Mapping`` or an object."""
    if isinstance(record, Mapping):
        return record.get(name)
    return getattr(record, name, None)


def _measurement_ids(record: Any) -> list[str]:
    """Measurement ids carried by a record: ``measurement_ids`` + ``measurement_id``."""
    out: list[str] = []
    many = _field(record, "measurement_ids")
    if isinstance(many, (list, tuple)):
        out.extend(str(m) for m in many if m is not None)
    one = _field(record, "measurement_id")
    if one is not None:
        out.append(str(one))
    return out


def synthesize_samples(records: Iterable[Any]) -> list[Sample]:
    """Fold flat extractor records into de-duplicated Sample nodes (§6.13).

    Records sharing an ``(experiment_id, material_id, regime_id)`` triplet
    collapse into one :class:`Sample` (deterministic id via
    :func:`make_sample_id`); their measurement ids are aggregated in first-seen
    order with duplicates removed, and the first non-``None`` ``doc_id`` is
    preserved. Groups are returned in first-seen order. An empty input yields
    ``[]``.
    """
    order: list[tuple[str | None, str | None, str | None]] = []
    groups: dict[tuple[str | None, str | None, str | None], dict[str, Any]] = {}

    for record in records:
        experiment_id = _field(record, "experiment_id")
        material_id = _field(record, "material_id")
        regime_id = _field(record, "regime_id")
        key = (experiment_id, material_id, regime_id)
        if key not in groups:
            groups[key] = {
                "experiment_id": experiment_id,
                "material_id": material_id,
                "regime_id": regime_id,
                "measurement_ids": [],
                "seen_measurements": set(),
                "doc_id": None,
            }
            order.append(key)
        acc = groups[key]
        for mid in _measurement_ids(record):
            if mid not in acc["seen_measurements"]:
                acc["seen_measurements"].add(mid)
                acc["measurement_ids"].append(mid)
        if acc["doc_id"] is None:
            doc_id = _field(record, "doc_id")
            if doc_id is not None:
                acc["doc_id"] = doc_id

    samples: list[Sample] = []
    for key in order:
        acc = groups[key]
        samples.append(
            Sample(
                sample_id=make_sample_id(
                    acc["experiment_id"], acc["material_id"], acc["regime_id"]
                ),
                experiment_id=acc["experiment_id"],
                material_id=acc["material_id"],
                regime_id=acc["regime_id"],
                measurement_ids=tuple(acc["measurement_ids"]),
                doc_id=acc["doc_id"],
            )
        )
    return samples


def _edge(source: Any, target: Any, rel: str, from_label: str, to_label: str) -> dict[str, Any]:
    """One declarative edge spec in the §6.13 ``{source, target, type, …}`` shape."""
    return {
        "source": source,
        "target": target,
        "type": rel,
        "from_label": from_label,
        "to_label": to_label,
    }


def sample_edges(sample: Sample) -> list[dict[str, Any]]:
    """Emit the link specs for a :class:`Sample` (§6.13).

    Produces, in order: ``HAS_SAMPLE`` (``Experiment → Sample``), ``OF_MATERIAL``
    (``Sample → Material``), ``UNDER_REGIME`` (``Sample → ProcessingRegime``) and
    one ``HAS_MEASUREMENT`` (``Sample → Measurement``) per aggregated measurement
    id. A missing material or regime simply omits that edge — the specimen is
    never linked to a nonexistent node.
    """
    edges: list[dict[str, Any]] = []
    if sample.experiment_id is not None:
        edges.append(
            _edge(
                sample.experiment_id,
                sample.sample_id,
                _REL_HAS_SAMPLE,
                _LABEL_EXPERIMENT,
                _LABEL_SAMPLE,
            )
        )
    if sample.material_id is not None:
        edges.append(
            _edge(
                sample.sample_id,
                sample.material_id,
                _REL_OF_MATERIAL,
                _LABEL_SAMPLE,
                _LABEL_MATERIAL,
            )
        )
    if sample.regime_id is not None:
        edges.append(
            _edge(
                sample.sample_id,
                sample.regime_id,
                _REL_UNDER_REGIME,
                _LABEL_SAMPLE,
                _LABEL_REGIME,
            )
        )
    for mid in sample.measurement_ids:
        edges.append(
            _edge(
                sample.sample_id,
                mid,
                _REL_HAS_MEASUREMENT,
                _LABEL_SAMPLE,
                _LABEL_MEASUREMENT,
            )
        )
    return edges
