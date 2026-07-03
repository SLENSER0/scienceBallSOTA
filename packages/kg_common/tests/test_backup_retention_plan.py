"""Tests for backup retention pruning planner — тесты обрезки бэкапов (§2.7)."""

from __future__ import annotations

from kg_common.backup_retention_plan import (
    BackupFile,
    RetentionPlan,
    parse_backup_name,
    plan_pruning,
)


def test_parse_backup_name_neo4j() -> None:
    parsed = parse_backup_name("neo4j-2026-07-01T00-00-00.dump")
    assert parsed is not None
    assert parsed.component == "neo4j"
    assert parsed.day == "2026-07-01"
    assert parsed.name == "neo4j-2026-07-01T00-00-00.dump"


def test_parse_backup_name_junk_is_none() -> None:
    assert parse_backup_name("junk.txt") is None


def test_parse_backup_name_missing_time_is_none() -> None:
    # No 'T' timestamp segment — не соответствует конвенции.
    assert parse_backup_name("neo4j-2026-07-01.dump") is None


def test_parse_backup_name_invalid_calendar_day_is_none() -> None:
    # Month 13 is not a real date — некорректная дата.
    assert parse_backup_name("pg-2026-13-01T00-00-00.dump") is None


def test_backup_file_as_dict() -> None:
    parsed = parse_backup_name("pg-2026-06-01T12-30-45.dump")
    assert parsed is not None
    assert parsed.as_dict() == {
        "name": "pg-2026-06-01T12-30-45.dump",
        "component": "pg",
        "day": "2026-06-01",
    }


def test_plan_pruning_deletes_old_file() -> None:
    plan = plan_pruning(["pg-2026-06-01T00-00-00.dump"], "2026-07-01", 7)
    assert plan.delete == ("pg-2026-06-01T00-00-00.dump",)
    assert plan.keep == ()


def test_plan_pruning_inclusive_boundary_kept() -> None:
    # Exactly keep_days back (7 days) — kept on the inclusive boundary.
    plan = plan_pruning(["pg-2026-06-24T00-00-00.dump"], "2026-07-01", 7)
    assert plan.keep == ("pg-2026-06-24T00-00-00.dump",)
    assert plan.delete == ()


def test_plan_pruning_one_day_past_boundary_deleted() -> None:
    # 8 days back with keep_days=7 — strictly older, deleted.
    plan = plan_pruning(["pg-2026-06-23T00-00-00.dump"], "2026-07-01", 7)
    assert plan.delete == ("pg-2026-06-23T00-00-00.dump",)
    assert plan.keep == ()


def test_plan_pruning_same_day_kept() -> None:
    plan = plan_pruning(["neo4j-2026-07-01T09-15-00.dump"], "2026-07-01", 7)
    assert plan.keep == ("neo4j-2026-07-01T09-15-00.dump",)
    assert plan.delete == ()


def test_plan_pruning_unparseable_always_kept() -> None:
    plan = plan_pruning(["notes.txt"], "2026-07-01", 7)
    assert "notes.txt" in plan.keep
    assert plan.delete == ()


def test_plan_pruning_sorted_tuples() -> None:
    names = [
        "pg-2026-07-01T00-00-00.dump",
        "neo4j-2026-07-01T00-00-00.dump",
        "pg-2026-01-01T00-00-00.dump",
        "neo4j-2026-01-01T00-00-00.dump",
        "readme.md",
        "notes.txt",
    ]
    plan = plan_pruning(names, "2026-07-01", 7)
    assert list(plan.keep) == sorted(plan.keep)
    assert list(plan.delete) == sorted(plan.delete)
    # Recent + unparseable kept; old dumps deleted.
    assert plan.keep == (
        "neo4j-2026-07-01T00-00-00.dump",
        "notes.txt",
        "pg-2026-07-01T00-00-00.dump",
        "readme.md",
    )
    assert plan.delete == (
        "neo4j-2026-01-01T00-00-00.dump",
        "pg-2026-01-01T00-00-00.dump",
    )


def test_plan_pruning_ok_true_and_as_dict() -> None:
    plan = plan_pruning(["pg-2026-06-01T00-00-00.dump"], "2026-07-01", 7)
    assert plan.ok is True
    d = plan.as_dict()
    assert d["ok"] is True
    assert d["delete"] == ["pg-2026-06-01T00-00-00.dump"]
    assert d["keep"] == []


def test_retention_plan_is_frozen() -> None:
    plan = RetentionPlan(keep=("a",), delete=(), ok=True)
    try:
        plan.ok = False  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject mutation
        raise AssertionError("RetentionPlan should be frozen")


def test_backup_file_is_frozen() -> None:
    bf = BackupFile(name="n", component="c", day="2026-07-01")
    try:
        bf.day = "2026-07-02"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject mutation
        raise AssertionError("BackupFile should be frozen")


def test_plan_pruning_empty_input() -> None:
    plan = plan_pruning([], "2026-07-01", 7)
    assert plan.keep == ()
    assert plan.delete == ()
    assert plan.ok is True
