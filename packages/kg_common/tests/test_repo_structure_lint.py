"""Тесты линтера структуры монорепо (§2.1 / §6.1)."""

from __future__ import annotations

from kg_common.repo_structure_lint import (
    REQUIRED_DIRS,
    StructureReport,
    check_structure,
)


def test_full_set_is_ok() -> None:
    """Полный набор §6.1 → missing пуст и ok=True."""
    report = check_structure(REQUIRED_DIRS)
    assert report.missing == ()
    assert report.ok is True
    assert set(report.present) == set(REQUIRED_DIRS)


def test_dropping_frontend_is_not_ok() -> None:
    """Убрать 'apps/frontend' → он в missing и ok=False."""
    existing = REQUIRED_DIRS - {"apps/frontend"}
    report = check_structure(existing)
    assert "apps/frontend" in report.missing
    assert report.ok is False
    assert "apps/frontend" not in report.present


def test_trailing_slash_matches() -> None:
    """'infra/' с хвостовым слэшем матчит эталон 'infra'."""
    existing = {p if p != "infra" else "infra/" for p in REQUIRED_DIRS}
    report = check_structure(existing)
    assert report.ok is True
    assert "infra" in report.present
    assert "infra" not in report.missing


def test_extra_path_does_not_affect_ok() -> None:
    """Лишний неродственный путь 'docs/user' не влияет на ok."""
    existing = set(REQUIRED_DIRS) | {"docs/user"}
    report = check_structure(existing)
    assert report.ok is True
    assert report.missing == ()
    assert "docs/user" not in report.present


def test_present_tuple_sorted() -> None:
    """present — отсортированный кортеж."""
    report = check_structure(REQUIRED_DIRS)
    assert list(report.present) == sorted(report.present)


def test_missing_tuple_sorted() -> None:
    """missing — отсортированный кортеж."""
    existing = {"infra"}
    report = check_structure(existing)
    assert list(report.missing) == sorted(report.missing)
    assert report.ok is False


def test_as_dict_round_trips_all_fields() -> None:
    """as_dict возвращает все три поля с совпадающими значениями."""
    existing = REQUIRED_DIRS - {"packages/kg_eval"}
    report = check_structure(existing)
    data = report.as_dict()
    assert data == {
        "missing": list(report.missing),
        "present": list(report.present),
        "ok": report.ok,
    }
    assert data["missing"] == ["packages/kg_eval"]
    assert data["ok"] is False


def test_report_is_frozen() -> None:
    """StructureReport заморожен — присваивание падает."""
    report = check_structure(REQUIRED_DIRS)
    assert isinstance(report, StructureReport)
    try:
        report.ok = False  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("StructureReport must be frozen")
