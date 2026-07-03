"""Tests for the retraction co-provenance watchlist (§25.12)."""

from __future__ import annotations

from kg_retrievers.retraction_provenance_watchlist import (
    Watchlist,
    WatchlistEntry,
    build_watchlist,
)


def test_shared_doc_id_flags_active_with_neighbor() -> None:
    """An active obs sharing ``doc_id`` with a retracted one is flagged (§25.12)."""
    active = [{"observation_id": "A", "doc_id": "D1", "author": "Ann"}]
    retracted = [{"observation_id": "R", "doc_id": "D1", "author": "Bob"}]
    wl = build_watchlist(active, retracted)
    assert wl.n_flagged == 1
    entry = wl.entries[0]
    assert entry.observation_id == "A"
    assert "doc_id" in entry.shared_keys
    assert "author" not in entry.shared_keys  # Ann != Bob
    assert entry.retracted_neighbors == ("R",)


def test_two_of_three_keys_risk() -> None:
    """Sharing 2 of 3 provenance keys gives ``risk == 2/3`` (§25.12)."""
    active = [{"observation_id": "A", "doc_id": "D1", "extraction_run_id": "X1", "author": "Ann"}]
    retracted = [
        {"observation_id": "R", "doc_id": "D1", "extraction_run_id": "X1", "author": "Zed"}
    ]
    wl = build_watchlist(active, retracted)
    assert wl.entries[0].risk == 2 / 3
    assert wl.entries[0].shared_keys == ("doc_id", "extraction_run_id")


def test_no_overlap_excluded_from_flagged() -> None:
    """An active obs sharing nothing is absent and not counted (§25.12)."""
    active = [
        {"observation_id": "A", "doc_id": "D1"},
        {"observation_id": "B", "doc_id": "D9", "author": "Nobody"},
    ]
    retracted = [{"observation_id": "R", "doc_id": "D1"}]
    wl = build_watchlist(active, retracted)
    ids = {e.observation_id for e in wl.entries}
    assert "B" not in ids
    assert wl.n_flagged == 1


def test_two_retracted_neighbors_listed_and_sorted() -> None:
    """Both retracted neighbors are listed and sorted (§25.12)."""
    active = [{"observation_id": "A", "doc_id": "D1", "author": "Ann"}]
    retracted = [
        {"observation_id": "R2", "doc_id": "D1"},
        {"observation_id": "R1", "author": "Ann"},
    ]
    wl = build_watchlist(active, retracted)
    entry = wl.entries[0]
    assert entry.retracted_neighbors == ("R1", "R2")
    assert set(entry.shared_keys) == {"doc_id", "author"}


def test_higher_risk_precedes_lower_risk() -> None:
    """A higher-risk entry sorts before a lower-risk one (§25.12)."""
    active = [
        {"observation_id": "low", "doc_id": "D1"},
        {"observation_id": "high", "doc_id": "D1", "extraction_run_id": "X1", "author": "Ann"},
    ]
    retracted = [
        {"observation_id": "R", "doc_id": "D1", "extraction_run_id": "X1", "author": "Ann"}
    ]
    wl = build_watchlist(active, retracted)
    assert [e.observation_id for e in wl.entries] == ["high", "low"]
    assert wl.entries[0].risk > wl.entries[1].risk


def test_empty_retracted_yields_empty_watchlist() -> None:
    """An empty retracted list yields no entries and zero flagged (§25.12)."""
    active = [{"observation_id": "A", "doc_id": "D1"}]
    wl = build_watchlist(active, [])
    assert wl.entries == ()
    assert wl.n_flagged == 0


def test_empty_provenance_values_do_not_match() -> None:
    """A shared *empty* provenance value is not treated as overlap (§25.12)."""
    active = [{"observation_id": "A", "doc_id": "", "author": None}]
    retracted = [{"observation_id": "R", "doc_id": "", "author": None}]
    wl = build_watchlist(active, retracted)
    assert wl.entries == ()
    assert wl.n_flagged == 0


def test_as_dict_round_trips_risk_as_float() -> None:
    """``as_dict()['entries'][0]['risk']`` round-trips as a float (§25.12)."""
    active = [{"observation_id": "A", "doc_id": "D1"}]
    retracted = [{"observation_id": "R", "doc_id": "D1"}]
    wl = build_watchlist(active, retracted)
    payload = wl.as_dict()
    risk = payload["entries"][0]["risk"]
    assert isinstance(risk, float)
    assert risk == 1 / 3
    assert payload["n_flagged"] == 1


def test_frozen_dataclasses() -> None:
    """``WatchlistEntry`` and ``Watchlist`` are frozen (§25.12)."""
    entry = WatchlistEntry(
        observation_id="A",
        shared_keys=("doc_id",),
        retracted_neighbors=("R",),
        risk=1 / 3,
    )
    wl = Watchlist(entries=(entry,), n_flagged=1)
    for obj, field in ((entry, "risk"), (wl, "n_flagged")):
        try:
            setattr(obj, field, 0)
        except AttributeError:
            pass
        else:  # pragma: no cover
            raise AssertionError("expected frozen dataclass")
