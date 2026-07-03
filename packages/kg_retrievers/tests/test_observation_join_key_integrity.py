"""Tests for §25.3 Observation join-key integrity audit."""

from __future__ import annotations

from kg_retrievers.observation_join_key_integrity import (
    REQUIRED_JOIN_KEYS,
    IntegrityReport,
    check_join_keys,
)


def _obs(oid: str, **keys: str) -> dict:
    return {"id": oid, **keys}


def _complete(oid: str) -> dict:
    return _obs(
        oid,
        extraction_run_id="run-1",
        extractor="llm-extract",
        extractor_version="1.2.3",
    )


def test_all_three_keys_is_complete() -> None:
    report = check_join_keys([_complete("obs-1")])
    assert report.n == 1
    assert report.n_complete == 1
    assert report.completeness == 1.0
    assert report.offenders == ()
    assert all(count == 0 for count in report.missing_by_key.values())


def test_missing_extractor_tallies_and_offends() -> None:
    obs = _obs(
        "obs-bad",
        extraction_run_id="run-1",
        extractor_version="1.2.3",
    )
    report = check_join_keys([obs])
    assert report.missing_by_key["extractor"] == 1
    assert report.missing_by_key["extraction_run_id"] == 0
    assert report.missing_by_key["extractor_version"] == 0
    assert "obs-bad" in report.offenders
    assert report.n_complete == 0
    assert report.completeness == 0.0


def test_empty_string_counts_as_missing() -> None:
    obs = _obs(
        "obs-blank",
        extraction_run_id="run-1",
        extractor="   ",
        extractor_version="1.2.3",
    )
    report = check_join_keys([obs])
    assert report.missing_by_key["extractor"] == 1
    assert report.offenders == ("obs-blank",)
    assert report.completeness == 0.0


def test_two_obs_one_incomplete_gives_half() -> None:
    good = _complete("obs-good")
    bad = _obs("obs-missing", extractor="llm-extract")
    report = check_join_keys([good, bad])
    assert report.n == 2
    assert report.n_complete == 1
    assert report.completeness == 0.5
    assert report.offenders == ("obs-missing",)
    # bad obs is missing two of the three required keys.
    assert report.missing_by_key["extraction_run_id"] == 1
    assert report.missing_by_key["extractor_version"] == 1
    assert report.missing_by_key["extractor"] == 0


def test_offenders_is_sorted() -> None:
    incomplete = [_obs(oid) for oid in ("obs-c", "obs-a", "obs-b")]
    report = check_join_keys(incomplete)
    assert report.offenders == ("obs-a", "obs-b", "obs-c")
    assert list(report.offenders) == sorted(report.offenders)


def test_empty_batch_is_vacuously_complete() -> None:
    report = check_join_keys([])
    assert report.n == 0
    assert report.n_complete == 0
    assert report.completeness == 1.0
    assert report.offenders == ()
    # missing_by_key still carries one zeroed slot per required key.
    assert set(report.missing_by_key) == set(REQUIRED_JOIN_KEYS)
    assert all(count == 0 for count in report.missing_by_key.values())


def test_as_dict_shape() -> None:
    report = check_join_keys([_complete("obs-1"), _obs("obs-2")])
    d = report.as_dict()
    assert isinstance(d["missing_by_key"], dict)
    assert isinstance(d["offenders"], list)
    assert d["n"] == 2
    assert d["n_complete"] == 1
    assert d["completeness"] == 0.5
    assert d["offenders"] == ["obs-2"]


def test_report_is_frozen() -> None:
    report = check_join_keys([_complete("obs-1")])
    assert isinstance(report, IntegrityReport)
    try:
        report.n = 99  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("IntegrityReport should be frozen")
