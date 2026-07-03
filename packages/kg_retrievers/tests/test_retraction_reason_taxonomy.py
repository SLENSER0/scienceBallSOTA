"""Tests for the retraction reason taxonomy — тесты таксономии причин (§25.12)."""

from __future__ import annotations

from kg_retrievers.retraction_reason_taxonomy import (
    ReasonBucket,
    ReasonTaxonomy,
    build_taxonomy,
    canonical_reason,
)


def _rec(reason: str, by: str = "u1", at: str = "2026-01-01") -> dict[str, str]:
    return {"reason": reason, "retracted_by": by, "retracted_at": at}


def test_canonical_reason_superseded() -> None:
    assert canonical_reason("superseded by v2") == "superseded"


def test_canonical_reason_error() -> None:
    assert canonical_reason("data entry error") == "error"


def test_canonical_reason_duplicate() -> None:
    assert canonical_reason("duplicate submission") == "duplicate"


def test_canonical_reason_withdrawn() -> None:
    assert canonical_reason("withdrawn at author request") == "withdrawn"


def test_canonical_reason_other() -> None:
    assert canonical_reason("random note") == "other"


def test_build_taxonomy_dominant_and_n_codes() -> None:
    records = [
        _rec("data entry error"),
        _rec("computational error"),
        _rec("wrong units"),
        _rec("duplicate submission"),
    ]
    tax = build_taxonomy(records)
    assert isinstance(tax, ReasonTaxonomy)
    assert tax.dominant_code == "error"
    assert tax.n_codes == 2
    assert tax.total == 4
    # Buckets sorted desc by count: error(3) then duplicate(1).
    assert [b.code for b in tax.buckets] == ["error", "duplicate"]
    assert tax.buckets[0].count == 3
    assert tax.buckets[1].count == 1


def test_shares_are_count_over_total_and_sum_to_one() -> None:
    records = [_rec("error one"), _rec("error two"), _rec("duplicate x")]
    tax = build_taxonomy(records)
    for bucket in tax.buckets:
        assert isinstance(bucket, ReasonBucket)
        assert bucket.share == bucket.count / tax.total
    assert abs(sum(b.share for b in tax.buckets) - 1.0) < 1e-9


def test_total_equals_len_records() -> None:
    records = [_rec("error"), _rec("obsolete"), _rec("random")]
    tax = build_taxonomy(records)
    assert tax.total == len(records)


def test_examples_capped_at_max_examples() -> None:
    records = [_rec(f"error number {i}") for i in range(6)]
    tax = build_taxonomy(records, max_examples=3)
    assert tax.n_codes == 1
    bucket = tax.buckets[0]
    assert bucket.count == 6
    assert len(bucket.examples) == 3
    assert bucket.examples == ["error number 0", "error number 1", "error number 2"]


def test_examples_default_cap_is_three() -> None:
    records = [_rec(f"error {i}") for i in range(5)]
    tax = build_taxonomy(records)
    assert len(tax.buckets[0].examples) == 3


def test_empty_records() -> None:
    tax = build_taxonomy([])
    assert tax.total == 0
    assert tax.dominant_code is None
    assert tax.n_codes == 0
    assert tax.buckets == []


def test_as_dict_round_trips() -> None:
    tax = build_taxonomy([_rec("error"), _rec("duplicate")])
    d = tax.as_dict()
    assert d["total"] == 2
    assert d["dominant_code"] in {"error", "duplicate"}
    assert d["n_codes"] == 2
    assert isinstance(d["buckets"], list)
    first = d["buckets"][0]
    assert set(first) == {"code", "count", "share", "examples"}
    assert isinstance(first["examples"], list)
