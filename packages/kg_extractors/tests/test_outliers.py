"""Statistical outlier detection over a measurement population (§7.7).

Hand-checked expectations. IQR quartiles use ``statistics.quantiles`` with
``method="inclusive"``; the robust z-score is ``(x - median)/(1.4826·MAD)``.
"""

from __future__ import annotations

from kg_extractors.outliers import (
    METHOD_IQR,
    METHOD_ROBUST_Z,
    OutlierFlag,
    detect_outliers,
    iqr_bounds,
    robust_zscore,
    unit_scale_suspect,
)


def _rows(material: str, prop: str, values: list[float]) -> list[dict[str, object]]:
    """Build population rows for one (material_class, property) cohort."""
    return [{"material_class": material, "property": prop, "value": v} for v in values]


def test_iqr_bounds_hand_computed() -> None:
    """Inclusive quartiles of [10..15,100] give Q1=11.5, Q3=14.5 ⇒ fence (7.0, 19.0)."""
    lo, hi = iqr_bounds([10, 11, 12, 13, 14, 15, 100])
    # Q1=11.5, Q3=14.5, IQR=3.0 → 11.5-4.5=7.0, 14.5+4.5=19.0
    assert lo == 7.0
    assert hi == 19.0


def test_iqr_flags_clear_high_outlier() -> None:
    """100 sits far above the (7.0, 19.0) IQR fence → flagged, IQR test involved (§7.7)."""
    rows = _rows("steel", "hardness", [10, 11, 12, 13, 14, 15, 100])
    flags = detect_outliers(rows)
    outliers = [f for f in flags if f.is_outlier]
    assert len(outliers) == 1
    assert outliers[0].value == 100.0
    assert METHOD_IQR in outliers[0].method  # "iqr" or "iqr+robust_z"
    # the in-cohort low value 10 is inside the fence and must not be flagged
    assert all(f.value != 10.0 or not f.is_outlier for f in flags)


def test_robust_zscore_mad_flags_extreme() -> None:
    """[1,2,3,4,5,100]: median 3.5, MAD 1.5 ⇒ z(100)=96.5/2.2239≈43.39, others |z|<3.5."""
    zs = robust_zscore([1, 2, 3, 4, 5, 100])
    assert len(zs) == 6
    assert abs(zs[-1] - 96.5 / (1.4826 * 1.5)) < 1e-9  # exact hand value
    assert abs(zs[-1]) > 3.5  # the 100 is flagged
    assert all(abs(z) < 3.5 for z in zs[:-1])  # the other five are not


def test_robust_zscore_mad_zero_guard() -> None:
    """A homogeneous group has MAD=0 → guarded ÷0, all scores collapse to 0.0 (§7.7)."""
    assert robust_zscore([5, 5, 5, 5]) == [0.0, 0.0, 0.0, 0.0]


def test_homogeneous_group_yields_no_outliers() -> None:
    """Tight, spread-free cohort → no value is an outlier (нет выбросов, §7.7)."""
    flags = detect_outliers(_rows("cu", "conductivity", [50, 50, 50, 50, 50]))
    assert len(flags) == 5
    assert not any(f.is_outlier for f in flags)


def test_per_group_isolation() -> None:
    """An outlier in cohort A must not taint cohort B — groups are judged apart (§7.7)."""
    rows = _rows("steel", "hardness", [140, 145, 150, 148, 900])  # 900 is wild in A
    rows += _rows("alu", "hardness", [30, 31, 32, 33, 34])  # tight, clean cohort B
    flags = detect_outliers(rows)
    a_outliers = [f for f in flags if f.group == ("steel", "hardness") and f.is_outlier]
    b_outliers = [f for f in flags if f.group == ("alu", "hardness") and f.is_outlier]
    assert len(a_outliers) == 1 and a_outliers[0].value == 900.0
    assert b_outliers == []  # cohort B untouched by A's outlier


def test_small_group_is_graceful_and_unflagged() -> None:
    """A cohort of n<4 (even with a wild value) is skipped, not crashed (§7.7)."""
    flags = detect_outliers(_rows("ti", "hardness", [10, 20, 5000]))  # n=3 < MIN_GROUP_SIZE
    assert len(flags) == 3
    assert not any(f.is_outlier for f in flags)  # too small to trust → nothing flagged


def test_unit_scale_suspect_x1000_true_same_order_false() -> None:
    """148000 vs ~148 is a ×1000 slip (True); 155 vs 148 is same-order (False) (§7.7)."""
    assert unit_scale_suspect(148000, 148) is True  # ratio 1000, log10 = 3.0
    assert unit_scale_suspect(155, 148) is False  # ratio ≈1.05, same order


def test_unit_scale_suspect_x10() -> None:
    """1480 vs typical ~148 is the canonical ×10 slip → True; exact match → False (§7.7)."""
    assert unit_scale_suspect(1480, 148) is True  # ratio 10, log10 = 1.0
    assert unit_scale_suspect(148, 148) is False  # ratio 1, log10 = 0.0


def test_outlier_flag_as_dict_shape() -> None:
    """OutlierFlag.as_dict exposes the five documented fields (§7.7)."""
    flags = detect_outliers(_rows("steel", "hardness", [10, 11, 12, 13, 14, 15, 100]))
    outlier = next(f for f in flags if f.is_outlier)
    d = outlier.as_dict()
    assert set(d.keys()) == {"value", "group", "method", "score", "is_outlier"}
    assert d["value"] == outlier.value
    assert d["group"] == ("steel", "hardness")
    assert d["is_outlier"] is True
    assert isinstance(outlier, OutlierFlag)


def test_empty_population_returns_empty() -> None:
    """An empty population yields no flags — [] (§7.7)."""
    assert detect_outliers([]) == []


def test_low_outlier_flagged_by_robust_z() -> None:
    """A single low outlier below the cohort is caught (robust z or IQR), value returned."""
    rows = _rows("steel", "hardness", [100, 101, 102, 103, 104, 105, 2])
    outliers = [f for f in detect_outliers(rows) if f.is_outlier]
    assert len(outliers) == 1
    assert outliers[0].value == 2.0
    assert outliers[0].method in {METHOD_IQR, METHOD_ROBUST_Z, "iqr+robust_z"}
