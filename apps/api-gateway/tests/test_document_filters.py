"""Тесты фильтров списка документов ``GET /documents`` (§14.9).

Проверяют разбор query-параметров, валидацию статуса, сериализацию
:meth:`DocumentFilters.as_dict` и предикат :func:`matches` (включая
ISO-сравнение границ дат).

Tests for the §14.9 ``GET /documents`` filters: query parsing, status
validation, :meth:`DocumentFilters.as_dict` serialisation, and the
:func:`matches` predicate (including ISO date-bound comparison).
"""

from __future__ import annotations

import pytest
from api_gateway.document_filters import (
    DOC_STATUSES,
    DocumentFilters,
    matches,
    parse_document_filters,
)


def test_doc_statuses_constant() -> None:
    """DOC_STATUSES содержит ровно пять статусов ингеста / exactly five."""
    assert frozenset({"queued", "running", "succeeded", "failed", "cancelled"}) == DOC_STATUSES


def test_parse_source_type() -> None:
    """source_type пробрасывается / source_type is passed through."""
    assert parse_document_filters({"source_type": "pdf"}).source_type == "pdf"


def test_parse_all_fields() -> None:
    """Все поля разбираются / all fields parse into the dataclass."""
    f = parse_document_filters(
        {
            "source_type": "pdf",
            "owner": "alice",
            "lab": "lab-a",
            "status": "succeeded",
            "date_from": "2020-01-01",
            "date_to": "2021-01-01",
        }
    )
    assert f == DocumentFilters(
        source_type="pdf",
        owner="alice",
        lab="lab-a",
        status="succeeded",
        date_from="2020-01-01",
        date_to="2021-01-01",
    )


def test_parse_empty() -> None:
    """Пустой query → все поля None / empty query → all None."""
    assert parse_document_filters({}) == DocumentFilters()


def test_parse_status_valid() -> None:
    """Каждый допустимый статус разбирается / each valid status parses."""
    for status in DOC_STATUSES:
        assert parse_document_filters({"status": status}).status == status


def test_parse_status_bogus_raises() -> None:
    """Недопустимый статус → ValueError / bogus status raises."""
    with pytest.raises(ValueError):
        parse_document_filters({"status": "bogus"})


def test_matches_source_type_true() -> None:
    """Совпадающий source_type проходит / matching source_type passes."""
    assert matches({"source_type": "pdf"}, parse_document_filters({"source_type": "pdf"}))


def test_matches_source_type_false() -> None:
    """Несовпадающий source_type отбраковывается / mismatch fails."""
    assert not matches({"source_type": "docx"}, parse_document_filters({"source_type": "pdf"}))


def test_matches_owner_false() -> None:
    """Несовпадающий owner отбраковывается / owner mismatch fails."""
    assert not matches({"owner": "lab-a"}, parse_document_filters({"owner": "lab-b"}))


def test_matches_owner_true() -> None:
    """Совпадающий owner проходит / owner match passes."""
    assert matches({"owner": "lab-a"}, parse_document_filters({"owner": "lab-a"}))


def test_matches_lab_and_status() -> None:
    """lab и status сравниваются на равенство / lab & status equality."""
    f = parse_document_filters({"lab": "lab-a", "status": "running"})
    assert matches({"lab": "lab-a", "status": "running"}, f)
    assert not matches({"lab": "lab-a", "status": "queued"}, f)
    assert not matches({"lab": "lab-b", "status": "running"}, f)


def test_matches_date_from_false() -> None:
    """created_at до date_from отбраковывается / before date_from fails."""
    assert not matches(
        {"created_at": "2020-01-01"}, parse_document_filters({"date_from": "2021-01-01"})
    )


def test_matches_date_from_true() -> None:
    """created_at на/после date_from проходит / on-or-after date_from passes."""
    f = parse_document_filters({"date_from": "2021-01-01"})
    assert matches({"created_at": "2021-01-01"}, f)
    assert matches({"created_at": "2022-06-15"}, f)


def test_matches_date_to() -> None:
    """created_at после date_to отбраковывается / after date_to fails."""
    f = parse_document_filters({"date_to": "2021-12-31"})
    assert matches({"created_at": "2021-06-01"}, f)
    assert not matches({"created_at": "2022-01-01"}, f)


def test_matches_date_range() -> None:
    """Диапазон дат: обе границы применяются / both bounds apply."""
    f = parse_document_filters({"date_from": "2021-01-01", "date_to": "2021-12-31"})
    assert matches({"created_at": "2021-06-01"}, f)
    assert not matches({"created_at": "2020-12-31"}, f)
    assert not matches({"created_at": "2022-01-01"}, f)


def test_matches_missing_created_at_fails_date_bound() -> None:
    """Отсутствие created_at при активной границе → False / missing fails."""
    assert not matches({}, parse_document_filters({"date_from": "2021-01-01"}))
    assert not matches({}, parse_document_filters({"date_to": "2021-01-01"}))


def test_matches_empty_filter_true() -> None:
    """Пустой фильтр пропускает любой документ / empty filter matches any."""
    assert matches({"source_type": "pdf", "owner": "x"}, parse_document_filters({}))
    assert matches({}, parse_document_filters({}))


def test_as_dict_drops_unset() -> None:
    """as_dict() опускает None-поля / as_dict drops unset keys."""
    assert parse_document_filters({}).as_dict() == {}
    assert parse_document_filters({"source_type": "pdf"}).as_dict() == {"source_type": "pdf"}
    full = parse_document_filters(
        {"source_type": "pdf", "owner": "a", "lab": "l", "status": "queued"}
    )
    assert full.as_dict() == {
        "source_type": "pdf",
        "owner": "a",
        "lab": "l",
        "status": "queued",
    }
