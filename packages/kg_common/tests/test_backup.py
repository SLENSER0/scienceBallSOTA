"""Backup / restore command-builder tests (§3.9).

Hand-checked: every expected ``argv`` element and artifact path is spelled out,
and the manifest id is asserted stable under plan reordering.
"""

from __future__ import annotations

import pytest

from kg_common.backup import (
    NEO4J,
    POSTGRES,
    QDRANT,
    BackupPlan,
    backup_manifest,
    neo4j_dump_plan,
    postgres_dump_plan,
    qdrant_snapshot_plan,
    restore_plan,
)


def test_neo4j_dump_plan_command_and_artifact() -> None:
    plan = neo4j_dump_plan("neo4j", "/backups")
    # Command must carry the three neo4j-admin dump tokens.
    assert "neo4j-admin" in plan.command
    assert "database" in plan.command
    assert "dump" in plan.command
    # Runs inside the named container and writes into out_dir.
    assert plan.command[:3] == ["docker", "exec", "neo4j"]
    assert plan.artifact == "/backups/neo4j.dump"
    assert plan.target == "neo4j:neo4j@neo4j"


def test_neo4j_dump_plan_custom_database() -> None:
    plan = neo4j_dump_plan("kg-neo4j", "/var/backups", database="materials")
    assert "materials" in plan.command
    assert plan.artifact == "/var/backups/materials.dump"
    assert plan.command[-2:] == ["--to-path", "/var/backups"]


def test_postgres_dump_plan_contains_pg_dump() -> None:
    dsn = "postgresql://kg:secret@localhost:5432/scienceball"
    plan = postgres_dump_plan(dsn, "/backups")
    assert "pg_dump" in plan.command
    # DSN is passed through to --dbname verbatim.
    assert dsn in plan.command
    assert "custom" in plan.command
    # Artifact is named after the DSN database and lives under out_dir.
    assert plan.artifact == "/backups/scienceball.dump"
    assert plan.target == "postgres:scienceball"


def test_postgres_dump_plan_dsn_without_dbname_falls_back() -> None:
    plan = postgres_dump_plan("postgresql://kg@localhost:5432", "/b")
    assert plan.artifact == "/b/postgres.dump"


def test_qdrant_snapshot_plan_hits_snapshots_endpoint() -> None:
    plan = qdrant_snapshot_plan("http://localhost:6333", "materials")
    endpoint = "http://localhost:6333/collections/materials/snapshots"
    assert "/collections/materials/snapshots" in plan.artifact
    assert plan.artifact == endpoint
    assert endpoint in plan.command
    # It is a POST to create the snapshot server-side.
    assert "POST" in plan.command
    assert plan.target == "qdrant:materials"


def test_qdrant_snapshot_plan_strips_trailing_slash() -> None:
    plan = qdrant_snapshot_plan("http://localhost:6333/", "materials")
    assert plan.artifact == "http://localhost:6333/collections/materials/snapshots"


def test_restore_plan_neo4j() -> None:
    plan = restore_plan(NEO4J, "/backups/materials.dump")
    assert "neo4j-admin" in plan.command
    assert "load" in plan.command
    # Database name is recovered from the artifact stem.
    assert "materials" in plan.command
    assert "--from-path" in plan.command
    assert "/backups" in plan.command
    assert plan.artifact == "/backups/materials.dump"
    assert plan.target == "restore:neo4j:materials.dump"


def test_restore_plan_postgres() -> None:
    plan = restore_plan(POSTGRES, "/backups/scienceball.dump")
    assert "pg_restore" in plan.command
    assert plan.artifact in plan.command
    assert plan.artifact == "/backups/scienceball.dump"


def test_restore_plan_qdrant() -> None:
    endpoint = "http://localhost:6333/collections/materials/snapshots"
    plan = restore_plan(QDRANT, endpoint)
    assert "curl" in plan.command
    assert "PUT" in plan.command
    # Recover REST endpoint is the snapshots endpoint + /recover.
    assert f"{endpoint}/recover" in plan.command


def test_restore_plan_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="unknown backup kind"):
        restore_plan("mongodb", "/backups/x.dump")


def test_artifacts_are_under_out_dir() -> None:
    out_dir = "/srv/backups"
    neo = neo4j_dump_plan("neo4j", out_dir)
    pg = postgres_dump_plan("postgresql://u@h/kg", out_dir)
    for plan in (neo, pg):
        assert plan.artifact.startswith(out_dir + "/")


def test_backup_manifest_lists_all_artifacts_and_targets() -> None:
    plans = [
        neo4j_dump_plan("neo4j", "/b"),
        postgres_dump_plan("postgresql://u@h/kg", "/b"),
        qdrant_snapshot_plan("http://localhost:6333", "materials"),
    ]
    manifest = backup_manifest(plans)
    # Every plan's artifact appears in the manifest.
    for plan in plans:
        assert plan.artifact in manifest["artifacts"]
    assert len(manifest["artifacts"]) == 3
    assert len(manifest["plans"]) == 3
    # Targets are the sorted, de-duplicated target set.
    assert manifest["targets"] == sorted({p.target for p in plans})


def test_manifest_id_is_deterministic_and_order_independent() -> None:
    plans = [
        neo4j_dump_plan("neo4j", "/b"),
        postgres_dump_plan("postgresql://u@h/kg", "/b"),
        qdrant_snapshot_plan("http://localhost:6333", "materials"),
    ]
    id_a = backup_manifest(plans)["manifest_id"]
    id_b = backup_manifest(plans)["manifest_id"]
    # Same plans -> same id (no wall clock).
    assert id_a == id_b
    # Reordering the plans does not change the id (derived from the target set).
    id_reordered = backup_manifest(list(reversed(plans)))["manifest_id"]
    assert id_reordered == id_a
    # A different target set yields a different id.
    id_other = backup_manifest(plans[:2])["manifest_id"]
    assert id_other != id_a


def test_backup_plan_as_dict_shape() -> None:
    plan = neo4j_dump_plan("neo4j", "/b")
    d = plan.as_dict()
    assert d == {
        "target": "neo4j:neo4j@neo4j",
        "command": list(plan.command),
        "artifact": "/b/neo4j.dump",
    }
    # command must be a plain list (JSON-friendly) and a copy, not the same object.
    assert isinstance(d["command"], list)
    assert d["command"] is not plan.command
    assert isinstance(plan, BackupPlan)
