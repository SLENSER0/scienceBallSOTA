"""Tests for compose profile consistency — тесты паритета профилей (§2.2)."""

from __future__ import annotations

from kg_common.compose_profiles import ProfileReport, check_profiles


def test_optional_service_without_profile_is_missing_and_not_ok() -> None:
    """An optional 'prometheus' with [] -> in missing_profile and ok False."""
    report = check_profiles(
        service_profiles={"prometheus": []},
        optional=["prometheus"],
        required=[],
        known_profiles=["observability"],
    )
    assert "prometheus" in report.missing_profile
    assert report.ok is False


def test_required_service_with_profile_is_stray() -> None:
    """A required 'api' declaring ['observability'] -> in stray_profile."""
    report = check_profiles(
        service_profiles={"api": ["observability"]},
        optional=[],
        required=["api"],
        known_profiles=["observability"],
    )
    assert "api" in report.stray_profile
    assert report.ok is False


def test_unknown_profile_pair_is_flagged() -> None:
    """A service with profile 'typo' not in known_profiles -> ('svc','typo')."""
    report = check_profiles(
        service_profiles={"svc": ["typo"]},
        optional=["svc"],
        required=[],
        known_profiles=["observability"],
    )
    assert ("svc", "typo") in report.unknown_profiles
    assert report.ok is False


def test_optional_service_with_known_profile_has_no_findings() -> None:
    """An optional service with ['observability'] (known) -> no findings."""
    report = check_profiles(
        service_profiles={"grafana": ["observability"]},
        optional=["grafana"],
        required=[],
        known_profiles=["observability"],
    )
    assert report.missing_profile == ()
    assert report.stray_profile == ()
    assert report.unknown_profiles == ()
    assert report.ok is True


def test_unknown_profiles_sorted_by_service_then_profile() -> None:
    """unknown_profiles sorted by (service, profile)."""
    report = check_profiles(
        service_profiles={
            "zeta": ["bad2"],
            "alpha": ["bad2", "bad1"],
        },
        optional=["zeta", "alpha"],
        required=[],
        known_profiles=[],
    )
    assert report.unknown_profiles == (
        ("alpha", "bad1"),
        ("alpha", "bad2"),
        ("zeta", "bad2"),
    )


def test_fully_consistent_input_is_ok() -> None:
    """A fully-consistent input -> ok True with empty findings."""
    report = check_profiles(
        service_profiles={
            "api": [],
            "db": [],
            "prometheus": ["observability"],
            "grafana": ["observability", "dashboards"],
        },
        optional=["prometheus", "grafana"],
        required=["api", "db"],
        known_profiles=["observability", "dashboards"],
    )
    assert report == ProfileReport(
        missing_profile=(),
        stray_profile=(),
        unknown_profiles=(),
        ok=True,
    )
    assert report.ok is True


def test_missing_and_stray_are_sorted() -> None:
    """missing_profile and stray_profile are sorted."""
    report = check_profiles(
        service_profiles={
            "zopt": [],
            "aopt": [],
            "zreq": ["observability"],
            "areq": ["observability"],
        },
        optional=["zopt", "aopt"],
        required=["zreq", "areq"],
        known_profiles=["observability"],
    )
    assert report.missing_profile == ("aopt", "zopt")
    assert report.stray_profile == ("areq", "zreq")
    assert report.ok is False


def test_as_dict_ok_is_bool() -> None:
    """as_dict()['ok'] is a bool and pairs serialise as lists."""
    report = check_profiles(
        service_profiles={"svc": ["typo"]},
        optional=["svc"],
        required=[],
        known_profiles=[],
    )
    payload = report.as_dict()
    assert isinstance(payload["ok"], bool)
    assert payload["ok"] is False
    assert payload["unknown_profiles"] == [["svc", "typo"]]
    assert payload["missing_profile"] == []


def test_report_is_frozen() -> None:
    """ProfileReport is frozen — immutability guarantee."""
    report = check_profiles(
        service_profiles={},
        optional=[],
        required=[],
        known_profiles=[],
    )
    try:
        report.ok = False  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("ProfileReport should be frozen")
