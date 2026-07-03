"""Tests for registry/catalog drift reconciliation — тесты сверки дрейфа (§10.12/§10.4)."""

from __future__ import annotations

from kg_common.metadata.catalog_reconcile import ReconcileReport, reconcile


def test_source_only_in_registry_is_missing_in_catalog() -> None:
    """A source present only in the registry appears in ``missing_in_catalog``."""
    report = reconcile({"s": 1}, {})
    assert report.missing_in_catalog == ("s",)
    assert report.orphan_in_catalog == ()
    assert report.version_mismatch == ()


def test_source_only_in_catalog_is_orphan() -> None:
    """A source present only in the catalog appears in ``orphan_in_catalog``."""
    report = reconcile({}, {"s": 1})
    assert report.orphan_in_catalog == ("s",)
    assert report.missing_in_catalog == ()
    assert report.version_mismatch == ()


def test_version_mismatch_reports_registry_then_catalog_version() -> None:
    """Registry ver 2 vs catalog ver 1 yields ``('s', 2, 1)``."""
    report = reconcile({"s": 2}, {"s": 1})
    assert report.version_mismatch == (("s", 2, 1),)
    assert report.missing_in_catalog == ()
    assert report.orphan_in_catalog == ()


def test_equal_versions_produce_no_entry_anywhere() -> None:
    """An id with equal versions on both sides drifts in no bucket."""
    report = reconcile({"s": 3}, {"s": 3})
    assert report.missing_in_catalog == ()
    assert report.orphan_in_catalog == ()
    assert report.version_mismatch == ()


def test_is_in_sync_true_when_maps_agree() -> None:
    """Identical maps are in sync — реестр и каталог совпадают."""
    assert reconcile({"a": 1}, {"a": 1}).is_in_sync() is True


def test_is_in_sync_false_on_any_mismatch() -> None:
    """A report carrying a version mismatch is not in sync."""
    report = reconcile({"a": 2}, {"a": 1})
    assert report.is_in_sync() is False


def test_is_in_sync_false_on_missing() -> None:
    """A report carrying a missing source is not in sync."""
    assert reconcile({"a": 1}, {}).is_in_sync() is False


def test_is_in_sync_false_on_orphan() -> None:
    """A report carrying an orphan source is not in sync."""
    assert reconcile({}, {"a": 1}).is_in_sync() is False


def test_missing_in_catalog_selects_only_registry_only_ids() -> None:
    """``{'a':1,'b':1}`` vs ``{'a':1}`` misses only ``b``."""
    report = reconcile({"a": 1, "b": 1}, {"a": 1})
    assert report.missing_in_catalog == ("b",)
    assert report.orphan_in_catalog == ()
    assert report.version_mismatch == ()


def test_all_result_tuples_are_sorted() -> None:
    """missing / orphan / mismatch tuples are each returned in sorted order."""
    registry = {"z": 9, "m": 2, "a": 1, "shared_hi": 5, "shared_lo": 7}
    catalog = {"q": 1, "b": 1, "shared_hi": 4, "shared_lo": 6}
    report = reconcile(registry, catalog)

    assert report.missing_in_catalog == ("a", "m", "z")
    assert list(report.missing_in_catalog) == sorted(report.missing_in_catalog)

    assert report.orphan_in_catalog == ("b", "q")
    assert list(report.orphan_in_catalog) == sorted(report.orphan_in_catalog)

    assert report.version_mismatch == (("shared_hi", 5, 4), ("shared_lo", 7, 6))
    assert list(report.version_mismatch) == sorted(report.version_mismatch)


def test_as_dict_round_trip_shape() -> None:
    """``as_dict`` renders every bucket as JSON-friendly lists."""
    report = reconcile({"a": 2, "b": 1}, {"a": 1, "c": 1})
    assert report.as_dict() == {
        "missing_in_catalog": ["b"],
        "orphan_in_catalog": ["c"],
        "version_mismatch": [["a", 2, 1]],
    }


def test_report_is_frozen() -> None:
    """The dataclass is immutable — заморожен."""
    report = ReconcileReport((), (), ())
    try:
        report.missing_in_catalog = ("x",)  # type: ignore[misc]
    except (AttributeError, TypeError):
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("ReconcileReport must be frozen")


def test_empty_maps_are_in_sync() -> None:
    """Two empty maps carry no drift."""
    report = reconcile({}, {})
    assert report.is_in_sync() is True
    assert report.as_dict() == {
        "missing_in_catalog": [],
        "orphan_in_catalog": [],
        "version_mismatch": [],
    }
