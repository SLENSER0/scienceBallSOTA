"""Tests for §10.3 business-glossary coverage vs canonical 24 core labels.

Тесты покрытия бизнес-глоссария. / Hand-checkable coverage assertions.
"""

from __future__ import annotations

from kg_common.metadata.catalog_glossary import all_labels
from kg_common.metadata.glossary_coverage import (
    GlossaryCoverage,
    assess_coverage,
    is_complete,
)


def test_canonical_has_24_labels() -> None:
    # §8.1 canonical registry — the coverage denominator. / Знаменатель покрытия.
    assert len(all_labels()) == 24


def test_empty_attached_covers_nothing() -> None:
    cov = assess_coverage([])
    assert cov.covered == ()
    assert cov.missing == all_labels()
    assert cov.unknown == ()
    assert cov.ratio == 0.0
    assert is_complete(cov) is False


def test_full_attached_is_complete() -> None:
    cov = assess_coverage(all_labels())
    assert cov.missing == ()
    assert cov.unknown == ()
    assert cov.covered == all_labels()
    assert cov.ratio == 1.0
    assert is_complete(cov) is True


def test_known_and_unknown_partitioned() -> None:
    cov = assess_coverage(["Material", "Bogus"])
    assert "Material" in cov.covered
    assert "Bogus" in cov.unknown
    assert "Material" not in cov.unknown
    assert "Bogus" not in cov.covered


def test_unknown_label_breaks_completeness_even_when_all_canonical_covered() -> None:
    # All canonical labels + one stray label → still not "full vocabulary". / Не полное.
    cov = assess_coverage([*all_labels(), "Bogus"])
    assert cov.missing == ()
    assert cov.unknown == ("Bogus",)
    assert is_complete(cov) is False


def test_duplicate_attached_counted_once() -> None:
    cov = assess_coverage(["Material", "Material"])
    assert cov.covered.count("Material") == 1
    assert cov.covered == ("Material",)


def test_covered_plus_missing_equals_canonical() -> None:
    cov = assess_coverage(["Material", "Alloy", "Bogus"])
    assert len(cov.covered) + len(cov.missing) == len(all_labels())


def test_missing_is_sorted_ascending() -> None:
    cov = assess_coverage(["Material"])
    assert list(cov.missing) == sorted(cov.missing)
    assert list(cov.covered) == sorted(cov.covered)
    assert list(cov.unknown) == sorted(cov.unknown)


def test_partial_ratio_strictly_between_zero_and_one() -> None:
    labels = all_labels()
    cov = assess_coverage(labels[:5])
    assert 0.0 < cov.ratio < 1.0
    assert cov.ratio == round(5 / len(labels), 6)


def test_as_dict_round_trips_fields() -> None:
    cov = assess_coverage(["Material", "Bogus"])
    d = cov.as_dict()
    assert d == {
        "covered": cov.covered,
        "missing": cov.missing,
        "unknown": cov.unknown,
        "ratio": cov.ratio,
    }
    assert set(d) == {"covered", "missing", "unknown", "ratio"}


def test_frozen_dataclass_is_immutable() -> None:
    cov = assess_coverage(["Material"])
    assert isinstance(cov, GlossaryCoverage)
    try:
        cov.ratio = 0.5  # type: ignore[misc]
    except (AttributeError, TypeError):
        pass
    else:  # pragma: no cover
        raise AssertionError("GlossaryCoverage must be frozen")
