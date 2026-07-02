"""Lab/experiment + materials-reference import (§20.1/§20.3/§20.4/§24.5)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from ingestion_service.lab_import import (
    import_experiment_catalog,
    import_materials_reference,
)

from kg_common import make_id
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph

EXPERIMENT_ROWS = [
    {
        "material": "никель катодный",
        "regime": "электроэкстракция",
        "equipment": "диафрагменная ванна",
        "property": "current_density",
        "value": 250,
        "unit": "А/м2",
        "date": "2024-03-11",
        "lab": "Лаборатория электрометаллургии",
        "expert": "Петров П.П.",
        "doc": "lab-protocol-ni-2024",
    },
    {
        "material": "католит",
        "regime": "циркуляция католита",
        "equipment": "диафрагменная ванна",
        "property": "flow_velocity",
        "value": "0,2",
        "unit": "м/с",
        "date": "2024-03-12",
        "lab": "Лаборатория электрометаллургии",
        "expert": "Петров П.П.",
        "doc": "lab-protocol-ni-2024",
    },
]

MATERIAL_ROWS = [
    {
        "material": "халькопирит",
        "material_class": "ore",
        "formula": "CuFeS2",
        "aliases": ["chalcopyrite", "халькопирит"],
        "domain": "pyrometallurgy",
    },
    {
        "material": "медный купорос",
        "class": "reagent",
        "formula": "CuSO4·5H2O",
    },
]


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(store)
    return store


def test_experiment_catalog_creates_evidence_backed_measurements() -> None:
    store = _store()
    try:
        res = import_experiment_catalog(store, EXPERIMENT_ROWS)
        assert res["experiments"] == 2
        assert res["measurements"] == 2
        # Experiment / Measurement / Equipment / Person nodes exist
        for label in ("Experiment", "Measurement", "Equipment", "Person", "Lab", "Sample"):
            rows = store.rows(
                "MATCH (n:Node) WHERE n.label=$l AND n.extractor_run_id='run:lab-import' "
                "RETURN count(n)",
                {"l": label},
            )
            assert rows[0][0] >= 1, label

        # canonical entity resolution: same equipment/expert across both rows -> one node
        equip_id = make_id("Equipment", "диафрагменная ванна")
        assert store.get_node(equip_id) is not None
        assert res["equipment"] == 1
        assert res["persons"] == 1
        assert res["labs"] == 1

        # every imported Measurement is evidence-backed (SUPPORTED_BY -> Evidence)
        orphan = store.rows(
            "MATCH (m:Node) WHERE m.label='Measurement' "
            "AND m.extractor_run_id='run:lab-import' "
            "AND NOT (m)-[:Rel]->(:Node {label:'Evidence'}) RETURN count(m)"
        )
        assert orphan[0][0] == 0

        # experiment shape wired: Experiment-[:MEASURED]->Measurement-[:OF_PROPERTY]->Property
        wired = store.rows(
            "MATCH (e:Node {label:'Experiment'})-[:Rel {type:'MEASURED'}]->"
            "(m:Node {label:'Measurement'})-[:Rel {type:'OF_PROPERTY'}]->"
            "(p:Node {label:'Property'}) RETURN count(*)"
        )
        assert wired[0][0] == 2

        # value normalization: current density persisted with a normalized value
        cd = store.rows(
            "MATCH (m:Node {label:'Measurement'}) WHERE m.property_name='current_density' "
            "AND m.extractor_run_id='run:lab-import' RETURN m.value_normalized"
        )
        assert cd and cd[0][0] == 250.0

        # idempotent re-import: no new nodes/rels
        before = store.counts()
        import_experiment_catalog(store, EXPERIMENT_ROWS)
        assert store.counts() == before
    finally:
        store.close()


def test_materials_reference_sets_class_and_formula() -> None:
    store = _store()
    try:
        res = import_materials_reference(store, MATERIAL_ROWS)
        assert res["materials"] == 2

        chalco = store.get_node(make_id("Material", "халькопирит"))
        assert chalco is not None
        assert chalco["material_class"] == "ore"
        assert chalco["formula"] == "CuFeS2"
        assert "chalcopyrite" in chalco.get("aliases_text", "")

        # ``class`` alias key also maps to material_class
        vitriol = store.get_node(make_id("Material", "медный купорос"))
        assert vitriol is not None
        assert vitriol["material_class"] == "reagent"
        assert vitriol["formula"] == "CuSO4·5H2O"

        # idempotent
        before = store.counts()
        import_materials_reference(store, MATERIAL_ROWS)
        assert store.counts() == before
    finally:
        store.close()
