"""Tests for §13.16 violation severity model / verifier_severity."""

from __future__ import annotations

from agent_service.verifier_severity import (
    RULE_SEVERITY,
    SEVERITY_RANK,
    SeverityReport,
    classify,
    severity_for,
)


def test_info_only_not_blocking() -> None:
    """(1) A report with only an ``info`` violation is non-blocking, max=='info'."""
    rep = classify([{"kind": "low_confidence"}])
    assert isinstance(rep, SeverityReport)
    assert rep.blocking is False
    assert rep.max_severity == "info"


def test_adding_block_flips_blocking_and_max() -> None:
    """(2) Adding ``numeric_claim_without_evidence`` flips blocking + max to block."""
    rep = classify(
        [
            {"kind": "low_confidence"},
            {"kind": "numeric_claim_without_evidence"},
        ]
    )
    assert rep.blocking is True
    assert rep.max_severity == "block"


def test_counts_sum_to_len_violations() -> None:
    """(3) ``counts`` sums to the number of violations."""
    violations = [
        {"kind": "low_confidence"},
        {"kind": "mixed_units"},
        {"kind": "unsupported_claim"},
        {"kind": "totally_unknown_kind"},
    ]
    rep = classify(violations)
    assert sum(rep.counts.values()) == len(violations)
    # Hand-checked: 1 info, 2 warn (mixed_units + unknown), 1 block.
    assert rep.counts == {"block": 1, "warn": 2, "info": 1}


def test_unknown_kind_defaults_to_warn() -> None:
    """(4) An unknown kind is tagged ``'warn'``."""
    rep = classify([{"kind": "not_a_real_kind"}])
    assert rep.violations[0]["severity"] == "warn"
    assert rep.max_severity == "warn"
    assert severity_for("not_a_real_kind") == "warn"


def test_empty_input() -> None:
    """(5) Empty input -> non-blocking, defined ``'none'`` max, all-zero counts."""
    rep = classify([])
    assert rep.blocking is False
    assert rep.max_severity == "none"
    assert rep.violations == ()
    assert set(rep.counts.values()) == {0}
    assert rep.counts == {"block": 0, "warn": 0, "info": 0}


def test_max_severity_obeys_rank_warn_over_info() -> None:
    """(6) Mixing warn + info yields max_severity 'warn' (rank obeyed)."""
    rep = classify([{"kind": "low_confidence"}, {"kind": "mixed_units"}])
    assert rep.max_severity == "warn"
    assert rep.blocking is False
    assert SEVERITY_RANK["warn"] > SEVERITY_RANK["info"]


def test_as_dict_preserves_order_and_injects_severity() -> None:
    """(7) as_dict()['violations'] keeps input order and carries injected severity."""
    violations = [
        {"kind": "low_confidence", "id": "a"},
        {"kind": "unsupported_claim", "id": "b"},
        {"kind": "mixed_units", "id": "c"},
    ]
    d = classify(violations).as_dict()
    out = d["violations"]
    assert [v["id"] for v in out] == ["a", "b", "c"]
    assert [v["severity"] for v in out] == ["info", "block", "warn"]
    # Original inputs are left untouched (classify copies each violation).
    assert "severity" not in violations[0]
    assert d["max_severity"] == "block"
    assert d["blocking"] is True


def test_rule_table_covers_spec_kinds() -> None:
    """§13.16 rule table maps the documented kinds to the documented severities."""
    assert RULE_SEVERITY == {
        "numeric_claim_without_evidence": "block",
        "unsupported_claim": "block",
        "mixed_units": "warn",
        "entity_substituted": "block",
        "unmarked_contradiction": "warn",
        "low_confidence": "info",
    }
