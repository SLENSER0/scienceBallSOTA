"""Tests for admin audit-log query filter + pagination — тесты (§19.5)."""

from __future__ import annotations

from kg_common.audit_query import AuditFilter, AuditPage, matches, query


def _rows() -> list[dict]:
    """A small, hand-checkable audit trail — набор записей аудита."""
    return [
        {"actor_id": "alice", "action": "delete", "target_type": "node", "ts": 100.0},
        {"actor_id": "bob", "action": "create", "target_type": "node", "ts": 200.0},
        {"actor_id": "alice", "action": "create", "target_type": "edge", "ts": 300.0},
        {"actor_id": "alice", "action": "delete", "target_type": "node", "ts": 400.0},
        {"actor_id": "carol", "action": "update", "target_type": "edge", "ts": 500.0},
    ]


def test_filter_by_actor_returns_only_that_actor() -> None:
    """(1) actor_id filter — только записи указанного актора."""
    page = query(_rows(), AuditFilter(actor_id="alice"))
    assert {r["actor_id"] for r in page.rows} == {"alice"}
    assert len(page.rows) == 3


def test_ts_from_is_inclusive_lower_bound() -> None:
    """(2) ts_from inclusive — нижняя граница включительна."""
    page = query(_rows(), AuditFilter(ts_from=300.0))
    assert {r["ts"] for r in page.rows} == {300.0, 400.0, 500.0}


def test_ts_to_is_inclusive_upper_bound() -> None:
    """(2) ts_to inclusive — верхняя граница включительна."""
    page = query(_rows(), AuditFilter(ts_to=300.0))
    assert {r["ts"] for r in page.rows} == {100.0, 200.0, 300.0}


def test_ts_from_and_ts_to_inclusive_window() -> None:
    """(2) both bounds inclusive — окно [ts_from, ts_to] включительно."""
    page = query(_rows(), AuditFilter(ts_from=200.0, ts_to=400.0))
    assert {r["ts"] for r in page.rows} == {200.0, 300.0, 400.0}


def test_action_filter_excludes_other_actions() -> None:
    """(3) action filter — исключает прочие действия."""
    page = query(_rows(), AuditFilter(action="delete"))
    assert {r["action"] for r in page.rows} == {"delete"}
    assert page.total == 2


def test_two_fields_combine_with_and() -> None:
    """(4) actor_id AND action — два критерия объединяются логическим И."""
    page = query(_rows(), AuditFilter(actor_id="alice", action="delete"))
    assert {r["ts"] for r in page.rows} == {100.0, 400.0}
    # bob's create and alice's create/update are excluded
    assert all(r["actor_id"] == "alice" and r["action"] == "delete" for r in page.rows)


def test_offset_and_limit_slice_sorted_list() -> None:
    """(5) offset/limit — срез отсортированного списка."""
    page = query(_rows(), AuditFilter(), offset=1, limit=2)
    # sorted desc by ts: 500, 400, 300, 200, 100 -> [400, 300]
    assert [r["ts"] for r in page.rows] == [400.0, 300.0]
    assert page.offset == 1
    assert page.limit == 2


def test_total_reflects_all_matches_not_page_length() -> None:
    """(6) total — все совпадения, а не длина страницы."""
    page = query(_rows(), AuditFilter(), offset=0, limit=2)
    assert len(page.rows) == 2
    assert page.total == 5


def test_rows_sorted_by_ts_descending() -> None:
    """(7) сортировка по ts по убыванию."""
    page = query(_rows(), AuditFilter())
    assert [r["ts"] for r in page.rows] == [500.0, 400.0, 300.0, 200.0, 100.0]


def test_all_none_filter_matches_every_row() -> None:
    """(8) пустой фильтр — совпадает с каждой записью."""
    rows = _rows()
    page = query(rows, AuditFilter())
    assert page.total == len(rows)
    assert len(page.rows) == len(rows)


def test_matches_all_none_true_for_any_row() -> None:
    """(8) matches() — all-None filter is always True."""
    assert matches({"anything": 1}, AuditFilter()) is True


def test_matches_target_type_field() -> None:
    """target_type filter narrows to one kind of object."""
    page = query(_rows(), AuditFilter(target_type="edge"))
    assert {r["target_type"] for r in page.rows} == {"edge"}
    assert page.total == 2


def test_filter_as_dict_round_trips() -> None:
    """AuditFilter.as_dict() carries all five criteria including None."""
    flt = AuditFilter(actor_id="alice", ts_from=1.0)
    d = flt.as_dict()
    assert d == {
        "actor_id": "alice",
        "action": None,
        "target_type": None,
        "ts_from": 1.0,
        "ts_to": None,
    }
    assert AuditFilter(**d) == flt


def test_page_as_dict_is_json_friendly() -> None:
    """AuditPage.as_dict() materializes rows as plain dict copies."""
    page = query(_rows(), AuditFilter(actor_id="carol"))
    d = page.as_dict()
    assert d["total"] == 1
    assert d["offset"] == 0
    assert d["limit"] == 50
    assert isinstance(d["rows"], list)
    assert d["rows"][0]["actor_id"] == "carol"


def test_page_rows_do_not_alias_input() -> None:
    """Mutating a returned row never touches the caller's input rows."""
    rows = _rows()
    page = query(rows, AuditFilter(actor_id="bob"))
    page.rows[0]["mutated"] = True
    assert all("mutated" not in r for r in rows)


def test_offset_beyond_total_yields_empty_page() -> None:
    """An offset past the end gives no rows but preserves total."""
    page = query(_rows(), AuditFilter(), offset=99, limit=10)
    assert page.rows == ()
    assert page.total == 5


def test_page_is_frozen_dataclass() -> None:
    """AuditPage is immutable — frozen dataclass."""
    import dataclasses

    import pytest

    page = AuditPage(rows=(), total=0, offset=0, limit=50)
    with pytest.raises(dataclasses.FrozenInstanceError):
        page.total = 1  # type: ignore[misc]
