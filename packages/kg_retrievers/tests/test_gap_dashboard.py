"""Gap-prioritization dashboard aggregation (§15.6).

Every assertion is hand-derivable. We seed four ``:Gap`` nodes in a temp
:class:`KuzuGraphStore` (``domain`` and ``gap_type`` are base columns; ``owner``
and the ``[0, 1]`` signals live in the JSON ``props`` catch-all, read back via
``get_node``). Each priority score follows the §15.9 weighted average
``score = 0.40·absence + 0.25·importance + 0.20·domain_criticality + 0.15·novelty``
with neutral default 0.5 for un-set signals and domain-criticality
water_treatment=1.0, energy=0.7, general=0.5:

- g1  absence 0.9, water_treatment → 0.36+0.125+0.20+0.075 = 0.76
- g2  absence 0.5, general         → 0.20+0.125+0.10+0.075 = 0.50
- g3  absence 0.1, water_treatment → 0.04+0.125+0.20+0.075 = 0.44
- g4  absence 0.3, energy          → 0.12+0.125+0.14+0.075 = 0.46
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.gap_dashboard import (
    UNKNOWN_DOMAIN,
    UNKNOWN_OWNER,
    GapDashboard,
    build_gap_dashboard,
)
from kg_retrievers.graph_store import KuzuGraphStore


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _gap(
    store: KuzuGraphStore,
    gid: str,
    *,
    gap_type: str,
    domain: str,
    owner: str,
    absence_confidence: float,
) -> None:
    store.upsert_node(
        gid,
        "Gap",
        name=f"пробел {gid}",
        gap_type=gap_type,
        domain=domain,
        owner=owner,
        absence_confidence=absence_confidence,
    )


def _seed_four(store: KuzuGraphStore) -> None:
    _gap(
        store,
        "gap:1",
        gap_type="missing_unit",
        domain="water_treatment",
        owner="alice",
        absence_confidence=0.9,
    )
    _gap(
        store,
        "gap:2",
        gap_type="missing_unit",
        domain="general",
        owner="bob",
        absence_confidence=0.5,
    )
    _gap(
        store,
        "gap:3",
        gap_type="orphan_entity",
        domain="water_treatment",
        owner="alice",
        absence_confidence=0.1,
    )
    _gap(
        store,
        "gap:4",
        gap_type="orphan_entity",
        domain="energy",
        owner="bob",
        absence_confidence=0.3,
    )


def test_by_domain_counts_are_correct(store: KuzuGraphStore) -> None:
    _seed_four(store)
    dash = build_gap_dashboard(store)
    assert dash.by_domain == {"water_treatment": 2, "general": 1, "energy": 1}


def test_by_type_counts_are_correct(store: KuzuGraphStore) -> None:
    _seed_four(store)
    dash = build_gap_dashboard(store)
    assert dash.by_type == {"missing_unit": 2, "orphan_entity": 2}


def test_by_owner_counts_are_correct(store: KuzuGraphStore) -> None:
    _seed_four(store)
    dash = build_gap_dashboard(store)
    assert dash.by_owner == {"alice": 2, "bob": 2}


def test_top_gaps_sorted_by_score_descending(store: KuzuGraphStore) -> None:
    _seed_four(store)
    dash = build_gap_dashboard(store)
    assert [g["id"] for g in dash.top_gaps] == ["gap:1", "gap:2", "gap:4", "gap:3"]
    scores = [g["score"] for g in dash.top_gaps]
    assert scores == [0.76, 0.50, 0.46, 0.44]
    assert scores == sorted(scores, reverse=True)


def test_each_top_gap_carries_score_and_explanation(store: KuzuGraphStore) -> None:
    _seed_four(store)
    dash = build_gap_dashboard(store)
    top = dash.top_gaps[0]
    assert top["id"] == "gap:1"
    assert top["score"] == pytest.approx(0.76)
    # RU explanation names the gap type and the priority word (§15.9 reuse).
    assert "приоритет" in top["explanation"]
    assert "missing_unit" in top["explanation"]
    for g in dash.top_gaps:
        assert isinstance(g["score"], float)
        assert g["explanation"]


def test_totals_equal_sum_of_grouped_counts(store: KuzuGraphStore) -> None:
    _seed_four(store)
    dash = build_gap_dashboard(store)
    assert dash.totals["gaps"] == 4
    assert dash.totals["gaps"] == sum(dash.by_domain.values())
    assert dash.totals["gaps"] == sum(dash.by_type.values())
    assert dash.totals["gaps"] == sum(dash.by_owner.values())
    assert dash.totals == {"gaps": 4, "domains": 3, "types": 2, "owners": 2}


def test_top_cap_is_respected(store: KuzuGraphStore) -> None:
    _seed_four(store)
    dash = build_gap_dashboard(store, top=2)
    assert len(dash.top_gaps) == 2
    assert [g["id"] for g in dash.top_gaps] == ["gap:1", "gap:2"]
    # capping the shortlist does not change the full grouped totals.
    assert dash.totals["gaps"] == 4


def test_empty_store_yields_zeros(store: KuzuGraphStore) -> None:
    dash = build_gap_dashboard(store)
    assert isinstance(dash, GapDashboard)
    assert dash.by_domain == {}
    assert dash.by_type == {}
    assert dash.by_owner == {}
    assert dash.top_gaps == []
    assert dash.totals == {"gaps": 0, "domains": 0, "types": 0, "owners": 0}


def test_missing_domain_and_owner_fall_back_to_ru_buckets(store: KuzuGraphStore) -> None:
    # A gap with no domain/owner columns still buckets under RU fallback labels.
    store.upsert_node("gap:x", "Gap", name="без метаданных", gap_type="missing_unit")
    dash = build_gap_dashboard(store)
    assert dash.by_domain == {UNKNOWN_DOMAIN: 1}
    assert dash.by_owner == {UNKNOWN_OWNER: 1}


def test_as_dict_round_trips_all_sections(store: KuzuGraphStore) -> None:
    _seed_four(store)
    d = build_gap_dashboard(store).as_dict()
    assert set(d) == {"by_domain", "by_type", "by_owner", "top_gaps", "totals"}
    assert d["by_type"] == {"missing_unit": 2, "orphan_entity": 2}
    assert d["top_gaps"][0]["id"] == "gap:1"
    assert d["totals"]["gaps"] == 4
