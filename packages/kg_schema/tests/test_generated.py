"""Generated LinkML/migrations stay in sync with the ontology (§3.2/§3.3/§3.10)."""

from __future__ import annotations

from pathlib import Path

import yaml

from kg_schema import NodeLabel

_ROOT = Path(__file__).resolve().parents[4]
_LINKML = _ROOT / "packages/kg_schema/src/kg_schema/linkml/kg_ontology.yaml"
_MIG = _ROOT / "infra/neo4j/migrations"


def test_linkml_covers_all_labels() -> None:
    if not _LINKML.exists():
        import pytest

        pytest.skip("run scripts/gen_schema_artifacts.py first")
    data = yaml.safe_load(_LINKML.read_text(encoding="utf-8"))
    classes = set(data["classes"])
    for label in NodeLabel:
        assert str(label) in classes, f"{label} missing from LinkML"
    assert data["classes"]["Material"]  # sanity
    assert len(data["enums"]) >= 15


def test_migrations_exist_and_cover_labels() -> None:
    if not (_MIG / "0001_constraints.cypher").exists():
        import pytest

        pytest.skip("run scripts/gen_schema_artifacts.py first")
    constraints = (_MIG / "0001_constraints.cypher").read_text(encoding="utf-8")
    for label in (NodeLabel.MATERIAL, NodeLabel.MEASUREMENT, NodeLabel.EVIDENCE):
        assert f"FOR (n:{label})" in constraints
    assert (_MIG / "0004_vector.cypher").exists()
