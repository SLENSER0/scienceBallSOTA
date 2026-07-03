"""Tests for §25.11 multi-document absence posterior (много-документный пробел)."""

from __future__ import annotations

from kg_retrievers.absence_multidoc import (
    MultiDocAbsence,
    combined_miss_probability,
    posterior_multidoc,
)


def test_combined_miss_two_halves() -> None:
    # (1 - 0.5) * (1 - 0.5) = 0.25
    assert combined_miss_probability([0.5, 0.5]) == 0.25


def test_combined_miss_empty_is_one() -> None:
    # Empty product: no extractor ran -> miss vacuously certain.
    assert combined_miss_probability([]) == 1.0


def test_combined_miss_two_high_recalls_rounds() -> None:
    # (1 - 0.9) * (1 - 0.9) = 0.01
    assert round(combined_miss_probability([0.9, 0.9]), 2) == 0.01


def test_single_doc_posterior_rounds() -> None:
    # combined_miss = 0.5; e=0.5 -> 0.5*0.5 / (0.5*0.5 + 0.5) = 0.25/0.75 = 0.333...
    got = posterior_multidoc(0.5, [0.5])
    assert round(got.p_extractor_missed, 3) == 0.333


def test_second_doc_lowers_missed_monotonic() -> None:
    one = posterior_multidoc(0.5, [0.5]).p_extractor_missed
    two = posterior_multidoc(0.5, [0.5, 0.5]).p_extractor_missed
    # More corroborating docs -> combined_miss shrinks -> empty cell less like a miss.
    assert two < one


def test_zero_prior_gives_certain_absence() -> None:
    got = posterior_multidoc(0.0, [0.5])
    assert got.p_truly_absent == 1.0
    assert got.p_extractor_missed == 0.0


def test_recall_one_collapses_miss() -> None:
    # A perfect extractor never misses -> combined_miss 0, so missed 0.
    got = posterior_multidoc(0.9, [0.5, 1.0, 0.3])
    assert got.combined_miss == 0.0
    assert got.p_extractor_missed == 0.0
    assert got.p_truly_absent == 1.0


def test_denominator_collapse_e_one_recall_one() -> None:
    # e=1 and combined_miss=0 -> denom 0 -> missed pinned to 0 (no divide-by-zero).
    got = posterior_multidoc(1.0, [1.0])
    assert got.p_extractor_missed == 0.0
    assert got.p_truly_absent == 1.0


def test_clamping_out_of_range_recalls() -> None:
    # Recalls clamped to [0, 1]: 1.5 -> 1.0 (miss factor 0), -0.5 -> 0.0 (factor 1).
    assert combined_miss_probability([1.5]) == 0.0
    assert combined_miss_probability([-0.5]) == 1.0


def test_all_outputs_within_unit_interval() -> None:
    cases = [
        (0.0, []),
        (0.5, [0.5]),
        (0.9, [0.1, 0.2, 0.9]),
        (1.0, [1.0]),
        (0.3, [0.0, 0.0]),
    ]
    for prior, recalls in cases:
        got = posterior_multidoc(prior, recalls)
        for val in (got.p_extractor_missed, got.p_truly_absent, got.combined_miss):
            assert 0.0 <= val <= 1.0


def test_posteriors_sum_to_one() -> None:
    got = posterior_multidoc(0.7, [0.4, 0.6])
    assert round(got.p_extractor_missed + got.p_truly_absent, 12) == 1.0


def test_n_docs_reflects_recall_count() -> None:
    assert posterior_multidoc(0.5, [0.4, 0.6, 0.7]).n_docs == 3
    assert posterior_multidoc(0.5, []).n_docs == 0


def test_dataclass_frozen_and_as_dict() -> None:
    got = posterior_multidoc(0.5, [0.5])
    assert isinstance(got, MultiDocAbsence)
    d = got.as_dict()
    assert set(d) == {"p_extractor_missed", "p_truly_absent", "combined_miss", "n_docs"}
    assert d["n_docs"] == 1
