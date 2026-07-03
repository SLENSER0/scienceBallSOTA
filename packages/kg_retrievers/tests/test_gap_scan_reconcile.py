"""Pure gap-scan reconciliation diff — hand-checkable buckets (§15.2/§15.6).

No store is needed: :func:`reconcile_scan` is a side-effect-free diff over two lists
of gap dicts keyed by ``dedup_key``. Every assertion below is verifiable by hand
against the lifecycle rules (created / reopened / auto_resolved / still_open).
"""

from __future__ import annotations

from kg_retrievers.gap_scan_reconcile import ScanReconciliation, reconcile_scan


def _prev(key: str, status: str) -> dict:
    return {"dedup_key": key, "status": status}


def _det(key: str) -> dict:
    return {"dedup_key": key}


def test_new_detected_key_is_created() -> None:
    # A key the previous scan never saw → created; the counter mirrors the bucket.
    rec = reconcile_scan(previous=[], detected=[_det("g:new")])
    assert rec.created == ("g:new",)
    assert len(rec.created) == 1
    assert rec.gaps_created == 1
    assert rec.reopened == () and rec.auto_resolved == ()


def test_resolved_key_reappearing_is_reopened() -> None:
    # A previously-resolved gap re-detected → reopened (снова открыт), not created.
    rec = reconcile_scan(previous=[_prev("g:1", "resolved")], detected=[_det("g:1")])
    assert rec.reopened == ("g:1",)
    assert len(rec.reopened) == 1
    assert rec.gaps_reopened == 1
    assert rec.created == ()  # it existed before, so never "created"
    assert rec.auto_resolved == ()


def test_open_key_disappearing_is_auto_resolved() -> None:
    # An open gap the fresh scan no longer detects → auto_resolved (покрыт).
    rec = reconcile_scan(previous=[_prev("g:1", "open")], detected=[])
    assert rec.auto_resolved == ("g:1",)
    assert len(rec.auto_resolved) == 1
    assert rec.gaps_auto_resolved == 1
    assert rec.still_open == ()


def test_dismissed_key_disappearing_is_not_auto_resolved() -> None:
    # A curator-dismissed gap that disappears is preserved: NOT auto_resolved, and it
    # stays in still_open (ручное решение сохраняется).
    rec = reconcile_scan(previous=[_prev("g:1", "dismissed")], detected=[])
    assert "g:1" not in rec.auto_resolved
    assert rec.auto_resolved == ()
    assert rec.gaps_auto_resolved == 0
    assert "g:1" in rec.still_open


def test_acknowledged_key_disappearing_is_preserved() -> None:
    # Same manual-preservation rule holds for 'acknowledged'.
    rec = reconcile_scan(previous=[_prev("g:1", "acknowledged")], detected=[])
    assert rec.auto_resolved == ()
    assert "g:1" in rec.still_open


def test_identical_open_and_detected_is_idempotent() -> None:
    # Re-running an unchanged scan: overlapping open keys → still_open, all three
    # event counters are 0 (idempotent per §15.6).
    prev = [_prev("g:1", "open"), _prev("g:2", "open")]
    det = [_det("g:1"), _det("g:2")]
    rec = reconcile_scan(previous=prev, detected=det)
    assert rec.gaps_created == 0
    assert rec.gaps_reopened == 0
    assert rec.gaps_auto_resolved == 0
    assert rec.created == () and rec.reopened == () and rec.auto_resolved == ()
    assert rec.still_open == ("g:1", "g:2")


def test_returned_tuples_are_sorted() -> None:
    # Buckets come back sorted regardless of input order.
    prev = [
        _prev("open:b", "open"),
        _prev("open:a", "open"),
        _prev("res:b", "resolved"),
        _prev("res:a", "resolved"),
    ]
    det = [_det("new:b"), _det("new:a"), _det("res:b"), _det("res:a")]
    rec = reconcile_scan(previous=prev, detected=det)
    assert rec.created == ("new:a", "new:b")
    assert rec.reopened == ("res:a", "res:b")
    assert rec.auto_resolved == ("open:a", "open:b")
    for bucket in (rec.created, rec.reopened, rec.auto_resolved, rec.still_open):
        assert list(bucket) == sorted(bucket)


def test_as_dict_exposes_the_three_int_counters() -> None:
    prev = [_prev("g:open", "open"), _prev("g:res", "resolved")]
    det = [_det("g:res"), _det("g:new")]
    rec = reconcile_scan(previous=prev, detected=det)
    d = rec.as_dict()
    # g:new → created, g:res → reopened, g:open (gone) → auto_resolved
    assert d["gaps_created"] == 1
    assert d["gaps_reopened"] == 1
    assert d["gaps_auto_resolved"] == 1
    counter_keys = ("gaps_created", "gaps_reopened", "gaps_auto_resolved")
    assert all(isinstance(d[k], int) for k in counter_keys)


def test_reconciliation_is_frozen() -> None:
    rec = reconcile_scan(previous=[], detected=[_det("g:1")])
    assert isinstance(rec, ScanReconciliation)
    import pytest

    with pytest.raises(AttributeError):
        rec.gaps_created = 99  # type: ignore[misc]


def test_missing_status_defaults_to_open() -> None:
    # A previous gap without a 'status' key is treated as open, so its disappearance
    # auto-resolves (matches a fresh Gap defaulting to open in gap_lifecycle).
    rec = reconcile_scan(previous=[{"dedup_key": "g:1"}], detected=[])
    assert rec.auto_resolved == ("g:1",)
    assert rec.gaps_auto_resolved == 1
