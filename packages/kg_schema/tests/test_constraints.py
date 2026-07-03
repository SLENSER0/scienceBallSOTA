"""Hand-checked tests for the declared graph-constraints catalog (§8.4 / §8.6).

Every expected value below is copied from the Neo4j migrations
(``infra/neo4j/migrations``) or read straight off :mod:`kg_schema.labels`, so the
assertions are concrete and hand-verifiable.
"""

from __future__ import annotations

import pytest

from kg_schema.constraints import (
    CONSTRAINTS,
    CORE_LABELS,
    VALID_KINDS,
    Constraint,
    ConstraintKind,
    constraint_names,
    constraints_by_kind,
    describe,
    to_cypher,
)
from kg_schema.labels import NodeLabel, RunLabel


def _by_name(name: str) -> Constraint:
    """Fetch a single catalog entry by its DDL object name."""
    matches = [c for c in CONSTRAINTS if c.name == name]
    assert len(matches) == 1, f"expected exactly one {name!r}, got {len(matches)}"
    return matches[0]


def test_every_core_label_has_unique_id_constraint() -> None:
    # §8.1: each of the 33 core labels must carry a REQUIRE id IS UNIQUE constraint.
    assert len(CORE_LABELS) == 33
    unique = {c.label: c for c in constraints_by_kind("unique")}
    for label in CORE_LABELS:
        c = unique[str(label)]
        assert c.properties == ("id",)
        assert c.name == f"{str(label).lower()}_id"
    # material_id / experiment_id / evidence_id are the §8.4-named ones.
    assert unique["Material"].name == "material_id"
    assert unique["Experiment"].name == "experiment_id"
    assert unique["Evidence"].name == "evidence_id"


def test_unique_constraints_cover_all_labels() -> None:
    # One uniqueness constraint per NodeLabel + RunLabel — derived from the enum.
    unique = constraints_by_kind("unique")
    expected = len(list(NodeLabel)) + len(list(RunLabel))
    assert len(unique) == expected == 46
    labels = {c.label for c in unique}
    # domain labels (§24.2) and run labels (§8.2) are included too.
    assert "TechnologySolution" in labels
    assert "ExtractorRun" in labels
    assert "GapScanRun" in labels


def test_entity_fulltext_index_present() -> None:
    ft = _by_name("entity_name_index")
    assert ft.kind == ConstraintKind.FULLTEXT == "fulltext"
    assert ft.properties == ("name", "canonical_name", "aliases_text")
    # Exactly the §8.4 label set, in migration order.
    assert ft.labels == (
        "Material",
        "Property",
        "Equipment",
        "Lab",
        "Person",
        "ProcessingRegime",
        "TechnologySolution",
    )


def test_to_cypher_unique_matches_migration() -> None:
    # Byte-identical to infra/neo4j/migrations/0001_constraints.cypher.
    assert to_cypher(_by_name("material_id")) == (
        "CREATE CONSTRAINT material_id IF NOT EXISTS FOR (n:Material) REQUIRE n.id IS UNIQUE;"
    )


def test_to_cypher_index_and_fulltext_text() -> None:
    assert to_cypher(_by_name("measurement_value_index")) == (
        "CREATE INDEX measurement_value_index IF NOT EXISTS "
        "FOR (n:Measurement) ON (n.value_normalized);"
    )
    # Byte-identical to infra/neo4j/migrations/0003_fulltext.cypher.
    assert to_cypher(_by_name("entity_name_index")) == (
        "CREATE FULLTEXT INDEX entity_name_index IF NOT EXISTS "
        "FOR (n:Material|Property|Equipment|Lab|Person|ProcessingRegime|TechnologySolution) "
        "ON EACH [n.name, n.canonical_name, n.aliases_text];"
    )


def test_to_cypher_exists_emits_not_null() -> None:
    # Existence constraint kind is supported by the emitter even if unused in the catalog.
    c = Constraint("evidence_id_exists", ConstraintKind.EXISTS, "Evidence", ("id",))
    assert to_cypher(c) == (
        "CREATE CONSTRAINT evidence_id_exists IF NOT EXISTS "
        "FOR (n:Evidence) REQUIRE n.id IS NOT NULL;"
    )


def test_to_cypher_rejects_unknown_kind() -> None:
    bad = Constraint("bogus", "vector", "Material", ("embedding",))
    with pytest.raises(ValueError, match="unknown constraint kind"):
        to_cypher(bad)


def test_all_kinds_valid_and_ddl_well_formed() -> None:
    assert {"unique", "index", "fulltext", "exists"} == VALID_KINDS
    for c in CONSTRAINTS:
        assert c.kind in VALID_KINDS
        ddl = to_cypher(c)
        assert ddl.startswith("CREATE ")
        assert "IF NOT EXISTS" in ddl
        assert ddl.endswith(";")
        assert c.properties, "every constraint must span at least one property"


def test_describe_shape() -> None:
    rows = describe()
    assert isinstance(rows, list)
    assert len(rows) == len(CONSTRAINTS)
    keys = {"name", "kind", "label", "labels", "properties", "cypher"}
    for row in rows:
        assert keys <= row.keys()
        assert isinstance(row["labels"], list)
        assert isinstance(row["properties"], list)
        assert row["cypher"].endswith(";")
    ft = next(r for r in rows if r["name"] == "entity_name_index")
    assert ft["kind"] == "fulltext"
    assert ft["labels"][0] == "Material"
    assert ft["cypher"] == to_cypher(_by_name("entity_name_index"))


def test_no_duplicate_label_property_kind() -> None:
    keys = [c.key() for c in CONSTRAINTS]
    assert len(keys) == len(set(keys)), "duplicate (label, properties, kind) in catalog"
    # Names are unique too — they become DDL object identifiers.
    names = constraint_names()
    assert len(names) == len(set(names))
    # Same label, different property is allowed (both ProcessingRegime range indexes).
    pr = {c.name for c in CONSTRAINTS if c.label == "ProcessingRegime" and c.kind == "index"}
    assert pr == {"processing_temperature_index", "processing_time_index"}


def test_constraint_as_dict_concrete() -> None:
    assert _by_name("material_id").as_dict() == {
        "name": "material_id",
        "kind": "unique",
        "label": "Material",
        "labels": ["Material"],
        "properties": ["id"],
    }
    assert _by_name("entity_name_index").as_dict() == {
        "name": "entity_name_index",
        "kind": "fulltext",
        "label": "Material|Property|Equipment|Lab|Person|ProcessingRegime|TechnologySolution",
        "labels": [
            "Material",
            "Property",
            "Equipment",
            "Lab",
            "Person",
            "ProcessingRegime",
            "TechnologySolution",
        ],
        "properties": ["name", "canonical_name", "aliases_text"],
    }
