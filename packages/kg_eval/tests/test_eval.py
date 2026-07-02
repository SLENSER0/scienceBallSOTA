"""Domain acceptance eval — all golden cases must pass deterministically (§24.18)."""

from __future__ import annotations

from kg_eval.golden import load_cases
from kg_eval.runner import run_suite


def test_all_cases_loaded() -> None:
    cases = load_cases("domain_science_ball")
    assert len(cases) >= 6
    ids = {c.id for c in cases}
    # the 4 mandatory acceptance queries (§24.22)
    assert {
        "water_desalination",
        "nickel_catholyte",
        "pgm_partitioning",
        "mine_water_injection",
    } <= ids


def test_suite_passes_deterministic() -> None:
    results = run_suite("domain_science_ball", use_llm=False)
    failed = [r.id for r in results if not r.passed]
    assert not failed, f"failed cases: {failed}"


def test_mandatory_four_high_recall() -> None:
    results = {r.id: r for r in run_suite("domain_science_ball", use_llm=False, check_parity=False)}
    for cid in (
        "water_desalination",
        "nickel_catholyte",
        "pgm_partitioning",
        "mine_water_injection",
    ):
        assert results[cid].entity_recall >= 0.75
        assert results[cid].passed
