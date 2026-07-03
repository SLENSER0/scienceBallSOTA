"""[DE] Deterministic synthetic Track-C corpus (spec §33.3, port of science_ball Dataset 1).

Seeds a :class:`~kg_retrievers.graph_store.KuzuGraphStore` with a corpus whose
ground truth is controlled **by construction**, and returns the matching
:class:`~kg_eval.schemas.DatasetManifest`. Every ``(material, property)`` cell is
generated from one of six archetypes that pins its true reality:

    PRESENT_TABLE   → present        (value in a document table → a Measurement)
    PRESENT_CATALOG → present        (value in the catalog → a Measurement)
    TRUE_MISS       → possible_miss  (value STATED in prose, no observation offline)
    FALSE_MISS      → genuine_gap    (property only NAMED in prose, no value)
    ABSENT          → genuine_gap    (never appears anywhere)
    RETRACTED       → retracted      (a Measurement, soft-retracted)

The ``FALSE_MISS`` vs ``TRUE_MISS`` contrast is the crux: a ``MENTIONS`` edge fires
for BOTH (the property is named in both), so a mention-based verdict cannot tell
them apart — exactly what the benchmark measures. Determinism is content-hash
based (SHA-1 mod 100), **no system RNG**, so a given ``(seed, n_materials)``
yields a byte-identical manifest.

Unlike the ``science_ball`` original (which wrote corpus files re-ingested by the
pipeline), this seeds the Kuzu graph directly with exactly the signals
:func:`~kg_retrievers.absence_signals.classify_cell` reads — Measurements (with
``value_normalized`` + ``ABOUT_MATERIAL``), soft-retractions, and prose
``Document→Chunk→(MENTIONS)→Property`` edges carrying ``value_present`` — so the
benchmark scores the real production absence layer end-to-end and offline.
"""

from __future__ import annotations

import hashlib
from typing import Any

from kg_eval.schemas import ARCHETYPE_LABEL, AbsenceCell, DatasetManifest, GoldExtractionFact
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.retractions import retract

# -- controlled vocabulary -------------------------------------------------
# Word-like names → clean, unambiguous entity linking.
_MATERIAL_NAMES: list[str] = [
    "Novasteel", "Ferralite", "Titanox", "Cupraloy", "Zircomet", "Magnalite",
    "Chromond", "Vanadex", "Niobrax", "Kobalten", "Tungstal", "Molybar",
    "Rhenite", "Palladex", "Osmiron", "Iridyte",
]  # fmt: skip

# (property_id, canonical_name, unit, aliases). Index order is load-bearing:
# 0=hardness, 1=strength, 2=elongation, 3=modulus. aliases[0] is the surface used
# in generated prose/tables.
PROPERTIES: list[tuple[str, str, str, list[str]]] = [
    (
        "prop_syn_hardness",
        "Vickers hardness (synthetic)",
        "HV",
        ["твердость по Виккерсу", "твердость", "HV", "hardness", "микротвердость"],
    ),
    (
        "prop_syn_strength",
        "Tensile strength (synthetic)",
        "MPa",
        ["предел прочности", "tensile strength", "прочность на разрыв", "UTS"],
    ),
    (
        "prop_syn_elongation",
        "Elongation (synthetic)",
        "percent",
        ["относительное удлинение", "elongation", "удлинение", "пластичность"],
    ),
    (
        "prop_syn_modulus",
        "Elastic modulus (synthetic)",
        "GPa",
        ["модуль упругости", "модуль Юнга", "Young's modulus", "elastic modulus"],
    ),
]

_BASE_VALUE = [180.0, 520.0, 8.0, 110.0]
_BASELINE = [150.0, 480.0, 11.0, 105.0]  # baseline < value except elongation
_DIRECTION = ["increase", "increase", "decrease", "increase"]

_REGIME: dict[str, Any] = {
    "regime_type": "aging",
    "temperature_C": 180,
    "time_min": 240,
    "atmosphere": "air",
}

# The ground-truth plan: 12 rows × 4 property columns, tiled across materials.
# Catalog archetypes (PRESENT_CATALOG/RETRACTED) are confined to properties 0-1 and
# ABSENT to properties 2-3 so ABSENT cells stay genuinely un-mentioned.
_SCHEDULE: list[list[str]] = [
    ["PRESENT_TABLE", "TRUE_MISS", "FALSE_MISS", "ABSENT"],
    ["PRESENT_CATALOG", "FALSE_MISS", "TRUE_MISS", "ABSENT"],
    ["PRESENT_TABLE", "PRESENT_CATALOG", "PRESENT_TABLE", "TRUE_MISS"],
    ["RETRACTED", "TRUE_MISS", "ABSENT", "FALSE_MISS"],
    ["PRESENT_CATALOG", "TRUE_MISS", "FALSE_MISS", "ABSENT"],
    ["TRUE_MISS", "PRESENT_CATALOG", "ABSENT", "TRUE_MISS"],
    ["PRESENT_TABLE", "FALSE_MISS", "TRUE_MISS", "ABSENT"],
    ["FALSE_MISS", "PRESENT_TABLE", "ABSENT", "FALSE_MISS"],
    ["RETRACTED", "PRESENT_CATALOG", "TRUE_MISS", "ABSENT"],
    ["PRESENT_CATALOG", "TRUE_MISS", "PRESENT_TABLE", "FALSE_MISS"],
    ["PRESENT_TABLE", "FALSE_MISS", "ABSENT", "TRUE_MISS"],
    ["TRUE_MISS", "PRESENT_TABLE", "FALSE_MISS", "ABSENT"],
]

_NOTES = [
    "Labels are pinned to the OFFLINE regime: with the LLM prose extractor on, "
    "TRUE_MISS cells become correctly-extracted 'present' — regenerate per profile.",
    "FALSE_MISS is the discriminator: property named but no measurable value → the "
    "correct verdict is genuine_gap, NOT possible_miss.",
]


def _jitter(seed: int, *parts: Any) -> int:
    """Deterministic 0..99 pseudo-jitter from a content hash (no system RNG)."""
    h = hashlib.sha1(("|".join(str(p) for p in (seed, *parts))).encode()).hexdigest()
    return int(h[:8], 16) % 100


def _round_value(pidx: int, seed: int, mat_id: str) -> float:
    base = _BASE_VALUE[pidx]
    delta = (_jitter(seed, mat_id, pidx) / 100.0 - 0.5) * (base * 0.15)
    return round(base + delta, 1)


def _material_name(i: int) -> str:
    if i < len(_MATERIAL_NAMES):
        return _MATERIAL_NAMES[i]
    return f"{_MATERIAL_NAMES[i % len(_MATERIAL_NAMES)]}{i // len(_MATERIAL_NAMES)}"


def _seed_measurement(
    store: KuzuGraphStore,
    i: int,
    pidx: int,
    mid: str,
    pid: str,
    value: float,
    unit: str,
    *,
    direction: str,
    evidence_doc_id: str,
    source_type: str,
) -> str:
    """A Measurement carrying a numeric value, attached to the material (→ present),
    backed by an Evidence span (doc + source_type) for Track-A semantic matching (D8)."""
    meas_id = f"meas_syn_{i:03d}_{pidx}"
    store.upsert_node(
        meas_id,
        "Measurement",
        name=pid,
        property_name=pid,
        value_normalized=value,
        unit=unit,
        direction=direction,
    )
    store.upsert_edge(meas_id, mid, "ABOUT_MATERIAL")
    ev_id = f"ev_syn_{i:03d}_{pidx}"
    store.upsert_node(ev_id, "Evidence", doc_id=evidence_doc_id, source_type=source_type)
    store.upsert_edge(meas_id, ev_id, "SUPPORTED_BY")
    return meas_id


def build_synthetic(
    store: KuzuGraphStore,
    *,
    n_materials: int = 12,
    seed: int = 20260701,
    name: str = "synthetic_v1",
    profile: str = "offline",
) -> DatasetManifest:
    """Seed ``store`` with the archetype corpus and return its ground-truth manifest.

    Deterministic: same ``(seed, n_materials)`` → identical manifest. All corpus
    signals are written directly to the graph (Measurements, retractions, prose
    MENTIONS edges with ``value_present``), so the real absence layer can be scored
    on it offline.
    """
    cells: list[AbsenceCell] = []
    gold: list[GoldExtractionFact] = []
    material_ids: list[str] = []
    property_ids = [p[0] for p in PROPERTIES]

    for pid, canonical, unit, aliases in PROPERTIES:
        store.upsert_node(
            pid,
            "Property",
            name=canonical,
            canonical_name=canonical,
            property_name=pid,
            unit=unit,
            aliases_text="|".join(aliases),
        )

    for i in range(n_materials):
        mid = f"mat_syn_{i:03d}"
        nm = _material_name(i)
        material_ids.append(mid)
        store.upsert_node(
            mid,
            "Material",
            name=nm,
            canonical_name=nm,
            aliases_text="|".join([f"{nm} alloy", f"сплав {nm}"]),
        )
        row = _SCHEDULE[i % len(_SCHEDULE)]
        doc_id = f"doc_syn_{i:03d}"
        chunk_id = f"chunk_syn_{i:03d}"
        prose_lines: list[str] = []
        prose_props: list[tuple[str, bool]] = []  # (property_id, value_present)

        for pidx, arch in enumerate(row):
            pid, canonical, unit, aliases = PROPERTIES[pidx]
            alias0 = aliases[0]
            value = _round_value(pidx, seed, mid)
            baseline = _BASELINE[pidx]
            direction = _DIRECTION[pidx]
            label = ARCHETYPE_LABEL[arch]
            modality: str | None = None
            stated: float | None = None
            mentioned = False
            measurable = False

            if arch == "PRESENT_TABLE":
                modality, stated, mentioned, measurable = "table_row", value, True, True
                _seed_measurement(
                    store,
                    i,
                    pidx,
                    mid,
                    pid,
                    value,
                    unit,
                    direction=direction,
                    evidence_doc_id=doc_id,
                    source_type="document_table_row",
                )
                gold.append(
                    GoldExtractionFact(
                        doc_id,
                        mid,
                        pid,
                        "document_table_row",
                        "table_row",
                        value,
                        unit,
                        dict(_REGIME),
                        baseline,
                        direction,
                        True,
                    )
                )
            elif arch == "PRESENT_CATALOG":
                modality, stated, mentioned, measurable = "catalog_row", value, False, True
                _seed_measurement(
                    store,
                    i,
                    pidx,
                    mid,
                    pid,
                    value,
                    unit,
                    direction=direction,
                    evidence_doc_id="doc_experiment_catalog",
                    source_type="catalog_row",
                )
                gold.append(
                    GoldExtractionFact(
                        "doc_experiment_catalog",
                        mid,
                        pid,
                        "catalog_row",
                        "catalog_row",
                        value,
                        unit,
                        dict(_REGIME),
                        baseline,
                        direction,
                        True,
                    )
                )
            elif arch == "TRUE_MISS":
                modality, stated, mentioned, measurable = "chunk", value, True, True
                verb = "повысило" if direction == "increase" else "снизило"
                prose_lines.append(
                    f"Для сплава {nm} старение при 180 °C также {verb} {alias0} до "
                    f"{value} {unit} по сравнению с исходным состоянием."
                )
                prose_props.append((pid, True))
                gold.append(
                    GoldExtractionFact(
                        doc_id,
                        mid,
                        pid,
                        "document_text",
                        "chunk",
                        value,
                        unit,
                        dict(_REGIME),
                        baseline,
                        direction,
                        False,
                    )
                )
            elif arch == "FALSE_MISS":
                modality, stated, mentioned, measurable = "chunk", None, True, False
                prose_lines.append(
                    f"Параметр «{alias0}» для сплава {nm} в данной кампании не измеряли; "
                    "измерение запланировано в будущей работе."
                )
                prose_props.append((pid, False))
            elif arch == "RETRACTED":
                modality, stated, mentioned, measurable = "catalog_row", value, False, True
                meas_id = _seed_measurement(
                    store,
                    i,
                    pidx,
                    mid,
                    pid,
                    value,
                    unit,
                    direction=direction,
                    evidence_doc_id="doc_experiment_catalog",
                    source_type="catalog_row",
                )
                retract(
                    store,
                    meas_id,
                    reason="benchmark retraction",
                    actor="loader_syn",
                    at="2026-06-15",
                )
            # ABSENT: nothing seeded.

            cells.append(
                AbsenceCell(
                    material_id=mid,
                    property_id=pid,
                    archetype=arch,
                    true_label=label,
                    measurable_in_source=measurable,
                    mentioned_in_source=mentioned,
                    source_modality=modality,
                    doc_id=(doc_id if modality in ("table_row", "chunk") else None),
                    stated_value=stated,
                    unit=unit,
                )
            )

        if prose_lines:
            intro = (
                f"Образцы {nm} подвергались старению при 180 °C в течение 4 ч на воздухе. "
                "Ниже приведены измеренные свойства."
            )
            store.upsert_node(
                doc_id, "Document", name=f"Synthetic report — {nm}", access_level="internal"
            )
            store.upsert_node(
                chunk_id, "Chunk", text=intro + "\n" + "\n".join(prose_lines), doc_id=doc_id
            )
            store.upsert_edge(doc_id, chunk_id, "HAS_CHUNK")
            store.upsert_edge(chunk_id, mid, "MENTIONS")
            for pid, vp in prose_props:
                store.upsert_edge(chunk_id, pid, "MENTIONS", value_present=vp)

    return DatasetManifest(
        name=name,
        seed=seed,
        profile=profile,
        cells=cells,
        extraction_gold=gold,
        materials=material_ids,
        properties=property_ids,
        notes=list(_NOTES),
    )
