#!/usr/bin/env python3
"""Generate schema deliverables from the authoritative kg_schema (§3.2, §3.10-3.13).

Emits:
  - packages/kg_schema/src/kg_schema/linkml/kg_ontology.yaml   (LinkML ontology)
  - infra/neo4j/migrations/0001_constraints.cypher            (uniqueness)
  - infra/neo4j/migrations/0002_indexes.cypher                (range/property)
  - infra/neo4j/migrations/0003_fulltext.cypher               (fulltext)
  - infra/neo4j/migrations/0004_vector.cypher                 (vector index)

Idempotent: running it twice yields identical files (keeps generated artifacts in
sync with labels/relationships/enums). Run: python scripts/gen_schema_artifacts.py
"""

from __future__ import annotations

import pathlib
from enum import StrEnum

import yaml

from kg_schema import EDGE_SCHEMA, ENTITY_LABELS, NodeLabel
from kg_schema import enums as E

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Common slots on all entities + the typed columns used for filtering.
COMMON_SLOTS = [
    "id",
    "name",
    "canonical_name",
    "aliases_text",
    "confidence",
    "review_status",
    "created_at",
    "schema_version",
    "extractor_run_id",
]
NUMERIC_SLOTS = {
    "Measurement": ["value_normalized", "normalized_unit", "value_raw", "unit"],
    "ProcessingRegime": ["temperature_c", "time_h", "operation", "atmosphere"],
    "TechnologySolution": ["operation", "domain", "practice_type", "country"],
    "Evidence": ["text", "doc_id", "page", "source_type", "evidence_strength"],
    "Paper": ["year", "practice_type", "country", "evidence_strength"],
    "Gap": ["gap_type", "domain"],
}


def _enum_defs() -> dict:
    out = {}
    for name in dir(E):
        obj = getattr(E, name)
        if isinstance(obj, type) and issubclass(obj, StrEnum) and obj is not StrEnum:
            out[name] = {"permissible_values": {str(v): {} for v in obj}}
    return out


def gen_linkml() -> None:
    classes: dict = {}
    for label in NodeLabel:
        slots = list(COMMON_SLOTS)
        slots += NUMERIC_SLOTS.get(str(label), [])
        classes[str(label)] = {
            "description": f"{label} node (§8.1).",
            "slots": sorted(set(slots)),
            "class_uri": f"kg:{label}",
            **({"mixins": ["Entity"]} if str(label) in ENTITY_LABELS else {}),
        }
    classes["Entity"] = {
        "abstract": True,
        "description": "Resolvable/embeddable super-label (§3.4).",
    }

    all_slots = sorted({s for c in classes.values() for s in c.get("slots", [])})
    schema = {
        "id": "https://science-ball.example/ontology",
        "name": "kg_ontology",
        "description": "Научный клубок — mining/metallurgy R&D knowledge-graph ontology.",
        "version": "0.1.0",
        "prefixes": {
            "kg": "https://science-ball.example/ontology#",
            "linkml": "https://w3id.org/linkml/",
            "schema": "https://schema.org/",
            "qudt": "http://qudt.org/schema/qudt/",
        },
        "default_prefix": "kg",
        "default_range": "string",
        "imports": ["linkml:types"],
        "slots": {
            s: {
                "description": s,
                **(
                    {"range": "float"}
                    if s in {"confidence", "value_normalized", "temperature_c", "time_h"}
                    else {}
                ),
                **({"range": "integer"} if s in {"year", "page"} else {}),
                **({"minimum_value": 0, "maximum_value": 1} if s == "confidence" else {}),
                **({"identifier": True} if s == "id" else {}),
            }
            for s in all_slots
        },
        "enums": _enum_defs(),
        "classes": classes,
        "_relationships": [
            {"from": str(f), "predicate": str(r), "to": str(t)} for f, r, t in EDGE_SCHEMA
        ],
    }
    out = ROOT / "packages/kg_schema/src/kg_schema/linkml/kg_ontology.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "# GENERATED from kg_schema by scripts/gen_schema_artifacts.py — DO NOT EDIT.\n"
        + yaml.safe_dump(schema, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print("wrote", out.relative_to(ROOT))


def gen_migrations() -> None:
    mig = ROOT / "infra/neo4j/migrations"
    mig.mkdir(parents=True, exist_ok=True)

    # 0001 constraints — uniqueness on id for every label + run labels
    lines = ["// GENERATED — uniqueness constraints (§3.10)"]
    for label in [*NodeLabel, "ExtractorRun", "GapScanRun"]:
        lines.append(
            f"CREATE CONSTRAINT {str(label).lower()}_id IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.id IS UNIQUE;"
        )
    (mig / "0001_constraints.cypher").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 0002 range/property indexes (§3.11)
    idx = [
        "// GENERATED — range/property indexes (§3.11)",
        "CREATE INDEX measurement_value_index IF NOT EXISTS FOR (m:Measurement) ON (m.value_normalized);",
        "CREATE INDEX processing_temperature_index IF NOT EXISTS FOR (r:ProcessingRegime) ON (r.temperature_c);",
        "CREATE INDEX processing_time_index IF NOT EXISTS FOR (r:ProcessingRegime) ON (r.time_h);",
        "CREATE INDEX evidence_review_index IF NOT EXISTS FOR (e:Evidence) ON (e.review_status);",
        "CREATE INDEX gap_type_index IF NOT EXISTS FOR (g:Gap) ON (g.gap_type);",
        "CREATE INDEX paper_year_index IF NOT EXISTS FOR (p:Paper) ON (p.year);",
        "CREATE INDEX tech_practice_index IF NOT EXISTS FOR (t:TechnologySolution) ON (t.practice_type);",
    ]
    (mig / "0002_indexes.cypher").write_text("\n".join(idx) + "\n", encoding="utf-8")

    # 0003 fulltext (§3.12)
    ft = [
        "// GENERATED — fulltext index (§3.12)",
        "CREATE FULLTEXT INDEX entity_name_index IF NOT EXISTS "
        "FOR (n:Material|Property|Equipment|Lab|Person|ProcessingRegime|TechnologySolution) "
        "ON EACH [n.name, n.canonical_name, n.aliases_text];",
        "CREATE FULLTEXT INDEX evidence_text_index IF NOT EXISTS "
        "FOR (n:Evidence|Claim) ON EACH [n.text];",
    ]
    (mig / "0003_fulltext.cypher").write_text("\n".join(ft) + "\n", encoding="utf-8")

    # 0004 vector (§3.13)
    vec = [
        "// GENERATED — vector index for :Entity embeddings (§3.13)",
        "CREATE VECTOR INDEX entity_embedding_index IF NOT EXISTS "
        "FOR (n:Entity) ON (n.embedding) "
        "OPTIONS { indexConfig: { `vector.dimensions`: 384, "
        "`vector.similarity_function`: 'cosine' } };",
    ]
    (mig / "0004_vector.cypher").write_text("\n".join(vec) + "\n", encoding="utf-8")
    print("wrote 4 migration files to", mig.relative_to(ROOT))


if __name__ == "__main__":
    gen_linkml()
    gen_migrations()
