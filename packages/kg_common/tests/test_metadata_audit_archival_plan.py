"""Tests for the audit-log archival planner — тесты плана архивации аудита (§10.8)."""

from __future__ import annotations

import pytest

from kg_common.metadata.audit_archival_plan import (
    ArchivePartition,
    object_key,
    partition_for,
    plan_archival,
)


def test_partition_for_datetime() -> None:
    assert partition_for("2026-07-03T10:00:00Z") == "2026-07"


def test_partition_for_date_only() -> None:
    assert partition_for("2026-05-01") == "2026-05"


def test_partition_for_bad_raises() -> None:
    with pytest.raises(ValueError):
        partition_for("bad")


def test_object_key_default_prefix() -> None:
    assert object_key("2026-07") == "kg-audit/2026-07/audit-2026-07.ndjson"


def test_object_key_custom_prefix() -> None:
    assert object_key("2026-07", prefix="backup") == "backup/2026-07/audit-2026-07.ndjson"


def test_plan_archival_empty() -> None:
    assert plan_archival([], "2026-07") == []


def test_plan_archival_older_record_included() -> None:
    records = [{"id": "a", "created_at": "2026-05-10T00:00:00Z"}]
    plan = plan_archival(records, "2026-07")
    assert plan == [
        ArchivePartition(
            year_month="2026-05",
            object_key="kg-audit/2026-05/audit-2026-05.ndjson",
            record_ids=("a",),
            count=1,
        )
    ]


def test_plan_archival_cutoff_month_retained() -> None:
    # A record in the cutoff month itself is retained (excluded), so the plan is empty.
    records = [{"id": "a", "created_at": "2026-07-01T00:00:00Z"}]
    assert plan_archival(records, "2026-07") == []


def test_plan_archival_groups_same_month_sorted() -> None:
    records = [
        {"id": "z", "created_at": "2026-05-20T00:00:00Z"},
        {"id": "a", "created_at": "2026-05-02T00:00:00Z"},
    ]
    plan = plan_archival(records, "2026-07")
    assert len(plan) == 1
    partition = plan[0]
    assert partition.year_month == "2026-05"
    assert partition.record_ids == ("a", "z")
    assert partition.count == 2


def test_plan_archival_multiple_months_ascending() -> None:
    records = [
        {"id": "june", "created_at": "2026-06-15T00:00:00Z"},
        {"id": "may", "created_at": "2026-05-15T00:00:00Z"},
    ]
    plan = plan_archival(records, "2026-07")
    assert [p.year_month for p in plan] == ["2026-05", "2026-06"]
    assert plan[0].record_ids == ("may",)
    assert plan[1].record_ids == ("june",)


def test_as_dict_shape() -> None:
    partition = ArchivePartition(
        year_month="2026-05",
        object_key="kg-audit/2026-05/audit-2026-05.ndjson",
        record_ids=("a", "b"),
        count=2,
    )
    assert partition.as_dict() == {
        "year_month": "2026-05",
        "object_key": "kg-audit/2026-05/audit-2026-05.ndjson",
        "record_ids": ["a", "b"],
        "count": 2,
    }
