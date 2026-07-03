"""Tests for the §5.10 / §5.12 batch ingestion report aggregator.

Тесты сводного отчёта пакетной загрузки: суммы, разбивка по статусам, детали ошибок.
"""

from __future__ import annotations

from ingestion_service.batch_ingest_report import BatchIngestReport, build_batch_report


def _sample_results() -> list[dict]:
    """Five documents: 2 done (one a duplicate), 2 failed, 1 skipped."""
    return [
        {"doc_id": "d1", "status": "done", "duplicate": False, "error": None},
        {"doc_id": "d2", "status": "done", "duplicate": True, "error": None},
        {"doc_id": "d3", "status": "failed", "duplicate": False, "error": "parse error"},
        {"doc_id": "d4", "status": "failed", "duplicate": False, "error": "timeout"},
        {"doc_id": "d5", "status": "skipped", "duplicate": False, "error": None},
    ]


def test_counts_are_hand_checkable() -> None:
    report = build_batch_report(_sample_results())
    assert report.total == 5
    assert report.done == 2
    assert report.failed == 2
    assert report.duplicates == 1


def test_by_status_tallies_every_status_and_sums_to_total() -> None:
    report = build_batch_report(_sample_results())
    assert report.by_status == {"done": 2, "failed": 2, "skipped": 1}
    assert sum(report.by_status.values()) == report.total


def test_each_failed_result_contributes_a_failure_entry() -> None:
    report = build_batch_report(_sample_results())
    assert report.failures == (
        {"doc_id": "d3", "error": "parse error"},
        {"doc_id": "d4", "error": "timeout"},
    )
    assert len(report.failures) == report.failed


def test_duplicate_truthiness_counted() -> None:
    results = [
        {"doc_id": "a", "status": "done", "duplicate": 1, "error": None},
        {"doc_id": "b", "status": "done", "duplicate": "yes", "error": None},
        {"doc_id": "c", "status": "done", "duplicate": 0, "error": None},
        {"doc_id": "d", "status": "done", "duplicate": None, "error": None},
    ]
    report = build_batch_report(results)
    assert report.duplicates == 2


def test_empty_input_yields_all_zero() -> None:
    report = build_batch_report([])
    assert report == BatchIngestReport(
        total=0,
        done=0,
        failed=0,
        duplicates=0,
        by_status={},
        failures=(),
    )
    assert report.by_status == {}
    assert report.failures == ()


def test_as_dict_is_json_safe_and_failures_is_a_list() -> None:
    report = build_batch_report(_sample_results())
    payload = report.as_dict()
    assert payload["total"] == 5
    assert payload["done"] == 2
    assert payload["failed"] == 2
    assert payload["duplicates"] == 1
    assert payload["by_status"] == {"done": 2, "failed": 2, "skipped": 1}
    assert isinstance(payload["failures"], list)
    assert payload["failures"] == [
        {"doc_id": "d3", "error": "parse error"},
        {"doc_id": "d4", "error": "timeout"},
    ]


def test_report_is_frozen() -> None:
    import dataclasses

    report = build_batch_report([])
    try:
        report.total = 99  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover
        raise AssertionError("BatchIngestReport must be frozen")
