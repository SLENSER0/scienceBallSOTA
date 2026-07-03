"""Тесты trust-weighted answer-support eval (§23.27) — RU/EN, hand-checkable."""

from __future__ import annotations

import dataclasses

import pytest

from kg_eval.trust_weighted_support import (
    ClaimTrust,
    TrustSupportReport,
    score_support,
)


def _claim(cid: str, supported: bool, status: str, trust: float) -> dict[str, object]:
    """Хелпер построения per-claim строки / build a per-claim row."""
    return {"id": cid, "supported": supported, "source_status": status, "trust": trust}


def test_all_supported_active_trust_one() -> None:
    """Все supported/active/trust=1.0 → weighted_support==1.0, warning False."""
    rep = score_support(
        [
            _claim("a", True, "active", 1.0),
            _claim("b", True, "active", 1.0),
        ]
    )
    assert rep.weighted_support == 1.0
    assert rep.warning is False
    assert rep.retracted_reliant_ids == ()
    assert rep.n == 2


def test_supported_retracted_never_counts() -> None:
    """Supported retracted → effective_support==0.0, retracted_reliant, warning."""
    rep = score_support([_claim("r", True, "retracted", 0.9)])
    assert rep.weighted_support == 0.0
    assert rep.warning is True
    assert rep.retracted_reliant_ids == ("r",)


def test_unsupported_active_is_zero() -> None:
    """Unsupported active → effective_support==0.0, без warning."""
    rep = score_support([_claim("u", False, "active", 1.0)])
    assert rep.weighted_support == 0.0
    assert rep.warning is False
    assert rep.retracted_reliant_ids == ()


def test_trust_half_supported_active_contributes_half() -> None:
    """trust=0.5 supported active → вклад 0.5."""
    rep = score_support([_claim("h", True, "active", 0.5)])
    assert rep.weighted_support == 0.5
    assert rep.warning is False


def test_superseded_treated_like_retracted() -> None:
    """superseded ведёт себя как retracted: не опора + warning."""
    rep = score_support([_claim("s", True, "superseded", 0.8)])
    assert rep.weighted_support == 0.0
    assert rep.warning is True
    assert rep.retracted_reliant_ids == ("s",)


def test_mixed_active_and_retracted_half() -> None:
    """[active1.0, retracted supported] → weighted_support==0.5, warning."""
    rep = score_support(
        [
            _claim("a", True, "active", 1.0),
            _claim("r", True, "retracted", 1.0),
        ]
    )
    assert rep.weighted_support == 0.5
    assert rep.warning is True
    assert rep.retracted_reliant_ids == ("r",)


def test_retracted_reliant_ids_sorted() -> None:
    """retracted_reliant_ids отсортированы вне зависимости от порядка входа."""
    rep = score_support(
        [
            _claim("z", True, "retracted", 1.0),
            _claim("a", True, "superseded", 1.0),
            _claim("m", True, "active", 1.0),
        ]
    )
    assert rep.retracted_reliant_ids == ("a", "z")


def test_corrected_active_counts_as_support() -> None:
    """corrected не входит в never-support: supported corrected засчитывается."""
    rep = score_support([_claim("c", True, "corrected", 0.4)])
    assert rep.weighted_support == pytest.approx(0.4)
    assert rep.warning is False
    assert rep.retracted_reliant_ids == ()


def test_empty_raises_value_error() -> None:
    """Пустой вход → ValueError."""
    with pytest.raises(ValueError):
        score_support([])


def test_invalid_status_raises() -> None:
    """Неизвестный source_status → ValueError."""
    with pytest.raises(ValueError):
        score_support([_claim("x", True, "bogus", 1.0)])


def test_trust_out_of_range_raises() -> None:
    """trust вне [0,1] → ValueError."""
    with pytest.raises(ValueError):
        score_support([_claim("x", True, "active", 1.5)])


def test_as_dict_shapes() -> None:
    """as_dict возвращает round-tripпируемые примитивы (RU/EN)."""
    ct = ClaimTrust(id="a", effective_support=0.5, retracted_reliant=False)
    assert ct.as_dict() == {
        "id": "a",
        "effective_support": 0.5,
        "retracted_reliant": False,
    }
    rep = TrustSupportReport(
        n=1,
        weighted_support=0.5,
        retracted_reliant_ids=("a",),
        warning=True,
    )
    assert rep.as_dict() == {
        "n": 1,
        "weighted_support": 0.5,
        "retracted_reliant_ids": ["a"],
        "warning": True,
    }


def test_report_is_frozen() -> None:
    """Отчёт заморожен (frozen dataclass)."""
    rep = score_support([_claim("a", True, "active", 1.0)])
    with pytest.raises(dataclasses.FrozenInstanceError):
        rep.weighted_support = 0.0  # type: ignore[misc]
