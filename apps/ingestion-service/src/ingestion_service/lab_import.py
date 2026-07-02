"""Lab/experiment + materials-reference catalog import (§20.1/§20.3/§20.4/§24.5).

Local, offline counterpart of the eLabFTW/openBIS connectors (§20.4/§20.5): turns
flat catalog rows — as exported from an ELN/LIMS or a curated spreadsheet — into an
evidence-first subgraph. Each experiment row materialises the canonical experiment
shape of §8.2::

    (:Experiment)-[:USES_SAMPLE]->(:Sample)-[:HAS_MATERIAL]->(:Material)
    (:Experiment)-[:PROCESSED_BY]->(:ProcessingRegime)
    (:Experiment)-[:USED_EQUIPMENT]->(:Equipment)
    (:Experiment)-[:PERFORMED_BY]->(:Person|:Lab)   (:Person)-[:MEMBER_OF]->(:Lab)
    (:Experiment)-[:MEASURED]->(:Measurement)-[:OF_PROPERTY]->(:Property)
    (:Measurement)-[:SUPPORTED_BY]->(:Evidence)     (:Paper)-[:REPORTS]->(:Experiment)

Every Measurement is evidence-backed: a synthetic :Evidence node (source_type
``metadata``, extractor ``lab_import_v1``) is created *before* the measurement is
linked, honouring the evidence-first invariant (§3.6/§8.3). IDs are deterministic
(``uuid5``/slug), so re-importing the same catalog is idempotent (§9.7).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from kg_common import evidence_id, get_logger, make_id, uuid5_id
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("lab_import")

SCHEMA_VERSION = "0.1.0"
RUN_ID = "run:lab-import"
EXTRACTOR = "lab_import_v1"


def _prov(now: str, **extra: Any) -> dict[str, Any]:
    """Common provenance fields for every node/edge written by this importer."""
    base: dict[str, Any] = {
        "extractor_run_id": RUN_ID,
        "schema_version": SCHEMA_VERSION,
        "created_at": now,
    }
    base.update(extra)
    return base


def _clean(value: Any) -> str | None:
    """Normalise a raw cell to a trimmed string, or None if empty."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_float(value: Any) -> float | None:
    """Best-effort numeric coercion of a measurement value (handles ``0,2`` / ``0.2``)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _normalize(value: float | None, unit: str | None) -> tuple[float | None, str | None]:
    """Canonicalise a value+unit via pint (§9.2 Step 5); fall back to the raw pair."""
    if value is None or not unit:
        return value, unit
    try:
        from kg_extractors.units import to_canonical

        norm = to_canonical(value, unit)
    except Exception:  # pragma: no cover - defensive: units pkg optional at import time
        norm = None
    if norm is None:
        return value, unit
    return norm.value, norm.unit


def import_experiment_catalog(
    store: KuzuGraphStore, rows: list[dict[str, Any]]
) -> dict[str, int]:
    """Import experiment/measurement catalog rows into the graph (evidence-first).

    Each ``row`` is a flat dict with keys ``material, regime, equipment, property,
    value, unit, date, lab, expert, doc`` (all optional except ``material`` +
    ``property``, which anchor the experiment/measurement). Returns counts of the
    distinct entities created plus graph totals.
    """
    now = datetime.now(UTC).isoformat()
    store.upsert_node(
        RUN_ID,
        "ExtractorRun",
        name="lab_import",
        **_prov(now, extractor=EXTRACTOR),
    )

    seen: dict[str, set[str]] = {
        "experiments": set(),
        "samples": set(),
        "measurements": set(),
        "materials": set(),
        "equipment": set(),
        "persons": set(),
        "labs": set(),
        "papers": set(),
        "evidence": set(),
    }

    for idx, row in enumerate(rows):
        material = _clean(row.get("material"))
        prop = _clean(row.get("property"))
        if not material or not prop:
            _log.warning("lab_import.skip_row", index=idx, reason="missing material/property")
            continue

        regime = _clean(row.get("regime"))
        equipment = _clean(row.get("equipment"))
        lab = _clean(row.get("lab"))
        expert = _clean(row.get("expert"))
        doc = _clean(row.get("doc")) or f"lab-catalog-row-{idx}"
        date = _clean(row.get("date"))
        unit = _clean(row.get("unit"))
        raw_value = row.get("value")
        value = _to_float(raw_value)
        value_raw = _clean(raw_value)

        # -- deterministic ids ------------------------------------------------
        exp_key = "|".join(
            str(x) for x in (material, regime, equipment, prop, value_raw, unit, date, doc)
        )
        exp_id = uuid5_id("Experiment", exp_key)
        sample_id = uuid5_id("Sample", exp_id, material)
        meas_id = uuid5_id("Measurement", exp_id, prop, value_raw, unit)
        material_id = make_id("Material", material)
        prop_id = make_id("Property", prop)
        paper_id = make_id("Paper", doc)

        # -- source / provenance nodes ---------------------------------------
        store.upsert_node(
            paper_id,
            "Paper",
            name=doc,
            canonical_name=doc,
            doc_id=doc,
            source_type="metadata",
            evidence_strength="experiment_protocol",
            **_prov(now, extractor=EXTRACTOR),
        )
        seen["papers"].add(paper_id)

        # -- entity nodes -----------------------------------------------------
        store.upsert_node(
            material_id,
            "Material",
            name=material,
            canonical_name=material,
            **_prov(now, confidence=0.7),
        )
        seen["materials"].add(material_id)

        store.upsert_node(
            prop_id,
            "Property",
            name=prop,
            canonical_name=prop,
            **_prov(now, confidence=0.7),
        )

        store.upsert_node(
            exp_id,
            "Experiment",
            name=f"{material}: {prop}" + (f" @ {regime}" if regime else ""),
            date_actualized=date,
            domain=_clean(row.get("domain")),
            **_prov(now, confidence=0.7),
        )
        seen["experiments"].add(exp_id)

        store.upsert_node(
            sample_id,
            "Sample",
            name=f"Проба: {material}",
            canonical_name=material,
            **_prov(now, confidence=0.7),
        )
        seen["samples"].add(sample_id)

        store.upsert_edge(exp_id, sample_id, "USES_SAMPLE", **_prov(now, confidence=0.9))
        store.upsert_edge(sample_id, material_id, "HAS_MATERIAL", **_prov(now, confidence=0.9))
        store.upsert_edge(paper_id, exp_id, "REPORTS", **_prov(now, confidence=0.9))

        if regime:
            regime_id = make_id("ProcessingRegime", regime)
            store.upsert_node(
                regime_id,
                "ProcessingRegime",
                name=regime,
                canonical_name=regime,
                **_prov(now, confidence=0.6),
            )
            store.upsert_edge(exp_id, regime_id, "PROCESSED_BY", **_prov(now, confidence=0.8))

        if equipment:
            equip_id = make_id("Equipment", equipment)
            store.upsert_node(
                equip_id,
                "Equipment",
                name=equipment,
                canonical_name=equipment,
                **_prov(now, confidence=0.6),
            )
            store.upsert_edge(exp_id, equip_id, "USED_EQUIPMENT", **_prov(now, confidence=0.8))
            seen["equipment"].add(equip_id)

        lab_id: str | None = None
        if lab:
            lab_id = make_id("Lab", lab)
            store.upsert_node(
                lab_id,
                "Lab",
                name=lab,
                canonical_name=lab,
                **_prov(now, confidence=0.7),
            )
            store.upsert_edge(exp_id, lab_id, "PERFORMED_BY", **_prov(now, confidence=0.8))
            seen["labs"].add(lab_id)

        if expert:
            person_id = make_id("Person", expert)
            store.upsert_node(
                person_id,
                "Person",
                name=expert,
                canonical_name=expert,
                **_prov(now, confidence=0.7),
            )
            store.upsert_edge(exp_id, person_id, "PERFORMED_BY", **_prov(now, confidence=0.8))
            if lab_id:
                store.upsert_edge(person_id, lab_id, "MEMBER_OF", **_prov(now, confidence=0.9))
            seen["persons"].add(person_id)

        # -- evidence-first measurement --------------------------------------
        norm_value, norm_unit = _normalize(value, unit)
        ev_text = (
            f"{prop} = {value_raw or 'н/д'}"
            + (f" {unit}" if unit else "")
            + f" для материала «{material}»"
            + (f" в режиме «{regime}»" if regime else "")
            + f"; источник: {doc}"
            + (f" ({date})" if date else "")
        )
        ev_id = evidence_id(paper_id, f"{meas_id}:{prop}", RUN_ID)
        store.upsert_node(
            ev_id,
            "Evidence",
            text=ev_text,
            doc_id=doc,
            source_type="metadata",
            evidence_strength="experiment_protocol",
            **_prov(now, extractor=EXTRACTOR, confidence=0.7),
        )
        seen["evidence"].add(ev_id)

        store.upsert_node(
            meas_id,
            "Measurement",
            name=prop,
            property_name=prop,
            value_normalized=norm_value,
            normalized_unit=norm_unit,
            value_raw=value_raw,
            unit=unit,
            date_actualized=date,
            **_prov(now, confidence=0.7),
        )
        seen["measurements"].add(meas_id)

        store.upsert_edge(exp_id, meas_id, "MEASURED", **_prov(now, confidence=0.9))
        store.upsert_edge(meas_id, prop_id, "OF_PROPERTY", **_prov(now, confidence=0.9))
        store.upsert_edge(
            meas_id, material_id, "ABOUT_MATERIAL", **_prov(now, confidence=0.8)
        )
        store.upsert_edge(
            meas_id,
            ev_id,
            "SUPPORTED_BY",
            **_prov(now, confidence=0.7, evidence_ids=[ev_id]),
        )

    totals = store.counts()
    result = {k: len(v) for k, v in seen.items()}
    result["rows"] = len(rows)
    result["nodes"] = totals["nodes"]
    result["rels"] = totals["rels"]
    return result


def import_materials_reference(
    store: KuzuGraphStore, rows: list[dict[str, Any]]
) -> dict[str, int]:
    """Upsert Material reference rows (``material_class``/``formula``) into the graph.

    Each ``row`` is a dict with ``material`` (or ``name``), and optional
    ``material_class``, ``formula``, ``aliases``, ``domain``. Returns counts.
    """
    now = datetime.now(UTC).isoformat()
    store.upsert_node(
        RUN_ID,
        "ExtractorRun",
        name="lab_import",
        **_prov(now, extractor=EXTRACTOR),
    )

    materials: set[str] = set()
    for idx, row in enumerate(rows):
        name = _clean(row.get("material")) or _clean(row.get("name"))
        if not name:
            _log.warning("materials_ref.skip_row", index=idx, reason="missing material name")
            continue
        material_id = make_id("Material", name)
        aliases = row.get("aliases")
        if isinstance(aliases, (list, tuple)):
            aliases_text = "|".join(str(a) for a in aliases if a)
        else:
            aliases_text = _clean(aliases)
        store.upsert_node(
            material_id,
            "Material",
            name=name,
            canonical_name=_clean(row.get("canonical_name")) or name,
            material_class=_clean(row.get("material_class")) or _clean(row.get("class")),
            formula=_clean(row.get("formula")),
            aliases_text=aliases_text,
            domain=_clean(row.get("domain")),
            **_prov(now, confidence=0.8),
        )
        materials.add(material_id)

    totals = store.counts()
    return {
        "rows": len(rows),
        "materials": len(materials),
        "nodes": totals["nodes"],
        "rels": totals["rels"],
    }
