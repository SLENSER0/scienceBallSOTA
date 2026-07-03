"""Tests for the feature-flag parity checker — тесты паритета флагов (§23.19)."""

from __future__ import annotations

from kg_common.feature_flag_parity import FlagDivergence, ParityReport, check


def test_uniform_enabled_is_in_parity() -> None:
    """Flag on in every env → in parity, no divergences."""
    report = check({"a", "b"}, {"dev": {"a"}, "prod": {"a"}})
    assert report.in_parity is True
    assert report.divergent == ()
    assert report.unknown_flags == ()
    assert report.environments == ("dev", "prod")


def test_single_divergence() -> None:
    """'b' on in dev, off in prod → one divergence."""
    report = check({"a", "b"}, {"dev": {"a", "b"}, "prod": {"a"}})
    assert report.in_parity is False
    assert len(report.divergent) == 1
    div = report.divergent[0]
    assert div.flag == "b"
    assert div.enabled_in == ("dev",)
    assert div.disabled_in == ("prod",)


def test_unknown_flag_sets_out_of_parity() -> None:
    """Enabled flag 'x' absent from registry → unknown, not in parity."""
    report = check({"a"}, {"dev": {"a", "x"}, "prod": {"a", "x"}})
    assert report.unknown_flags == ("x",)
    assert report.in_parity is False
    # 'x' is uniformly enabled so it is NOT a divergence, only unknown.
    assert report.divergent == ()


def test_identical_across_three_envs() -> None:
    """Same flag set in all three envs → in parity."""
    envs = {"dev": {"a", "b"}, "stage": {"a", "b"}, "prod": {"a", "b"}}
    report = check({"a", "b"}, envs)
    assert report.in_parity is True
    assert report.divergent == ()
    assert report.environments == ("dev", "prod", "stage")


def test_divergent_tuple_sorted_by_flag() -> None:
    """Multiple divergences come back sorted by flag name."""
    envs = {"dev": {"a", "c", "b"}, "prod": {"z"}}
    report = check({"a", "b", "c", "z"}, envs)
    flags = [d.flag for d in report.divergent]
    assert flags == sorted(flags)
    assert flags == ["a", "b", "c", "z"]


def test_empty_env_flags_is_in_parity() -> None:
    """No environments → nothing can diverge, in parity."""
    report = check({"a", "b"}, {})
    assert report.in_parity is True
    assert report.divergent == ()
    assert report.unknown_flags == ()
    assert report.environments == ()


def test_unknown_flags_sorted_and_deduplicated() -> None:
    """Unknown flags across envs are sorted and deduped."""
    envs = {"dev": {"y", "x"}, "prod": {"x", "z"}}
    report = check(set(), envs)
    assert report.unknown_flags == ("x", "y", "z")
    assert report.in_parity is False


def test_divergence_as_dict() -> None:
    """FlagDivergence.as_dict() round-trips fields to plain lists."""
    div = FlagDivergence(flag="b", enabled_in=("dev",), disabled_in=("prod",))
    assert div.as_dict() == {
        "flag": "b",
        "enabled_in": ["dev"],
        "disabled_in": ["prod"],
    }


def test_report_as_dict() -> None:
    """ParityReport.as_dict() nests divergences and lists tuples."""
    report = check({"a", "b"}, {"dev": {"a", "b"}, "prod": {"a"}})
    assert report.as_dict() == {
        "environments": ["dev", "prod"],
        "unknown_flags": [],
        "divergent": [
            {"flag": "b", "enabled_in": ["dev"], "disabled_in": ["prod"]},
        ],
        "in_parity": False,
    }


def test_report_is_frozen() -> None:
    """ParityReport is immutable — frozen dataclass."""
    report = check({"a"}, {"dev": {"a"}})
    try:
        report.in_parity = True  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("ParityReport should be frozen")
    assert isinstance(report, ParityReport)


def test_divergence_across_three_envs_enabled_disabled_split() -> None:
    """Enabled_in / disabled_in each collect the right envs, sorted."""
    envs = {"dev": {"f"}, "stage": {"f"}, "prod": set()}
    report = check({"f"}, envs)
    assert len(report.divergent) == 1
    div = report.divergent[0]
    assert div.enabled_in == ("dev", "stage")
    assert div.disabled_in == ("prod",)
