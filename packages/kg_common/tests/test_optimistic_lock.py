"""Tests for optimistic concurrency check — optimistic-lock (§16.9)."""

from __future__ import annotations

from kg_common.storage.optimistic_lock import (
    ConcurrencyCheck,
    check_version,
    next_version,
)


def test_match_ok_200() -> None:
    """Equal versions → запись разрешена (200)."""
    res = check_version(3, 3)
    assert res.ok is True
    assert res.status == 200
    assert isinstance(res, ConcurrencyCheck)


def test_mismatch_conflict_409() -> None:
    """Stale expected_version → 409 Conflict."""
    res = check_version(3, 2)
    assert res.ok is False
    assert res.status == 409


def test_none_no_precondition_ok() -> None:
    """No If-Match and not required → запись разрешена."""
    res = check_version(3, None)
    assert res.ok is True
    assert res.status == 200


def test_none_required_428() -> None:
    """Missing mandatory If-Match → 428 Precondition Required."""
    res = check_version(3, None, require=True)
    assert res.ok is False
    assert res.status == 428


def test_next_version() -> None:
    """next_version bumps by one."""
    assert next_version(3) == 4
    assert next_version(0) == 1


def test_versions_echoed() -> None:
    """current_version and expected_version are echoed into the dataclass."""
    res = check_version(7, 5)
    assert res.current_version == 7
    assert res.expected_version == 5


def test_none_expected_echoed_as_sentinel() -> None:
    """Omitted expected_version is echoed as -1 (serialisable sentinel)."""
    res = check_version(3, None)
    assert res.expected_version == -1
    assert res.current_version == 3


def test_as_dict_detail_nonempty_on_409() -> None:
    """as_dict() exposes a non-empty detail string on the conflict case."""
    d = check_version(3, 2).as_dict()
    assert isinstance(d["detail"], str)
    assert len(d["detail"]) > 0
    assert d["status"] == 409
    assert d["ok"] is False


def test_as_dict_detail_nonempty_on_428() -> None:
    """as_dict() exposes a non-empty detail string on the precondition-required case."""
    d = check_version(3, None, require=True).as_dict()
    assert isinstance(d["detail"], str)
    assert len(d["detail"]) > 0


def test_as_dict_detail_empty_on_ok() -> None:
    """Success cases carry an empty detail — no error to report."""
    assert check_version(3, 3).as_dict()["detail"] == ""
    assert check_version(3, None).as_dict()["detail"] == ""


def test_frozen_dataclass_immutable() -> None:
    """ConcurrencyCheck is frozen — попытка мутации падает."""
    res = check_version(3, 3)
    try:
        res.ok = False  # type: ignore[misc]
    except Exception as exc:
        assert "frozen" in str(exc).lower() or "cannot assign" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("expected frozen dataclass to reject mutation")


def test_as_dict_roundtrip_keys() -> None:
    """as_dict() carries exactly the five spec fields."""
    d = check_version(3, 3).as_dict()
    assert set(d) == {"ok", "status", "current_version", "expected_version", "detail"}
