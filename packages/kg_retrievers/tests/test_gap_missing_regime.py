"""§15.3 ``missing_regime`` gap subtype — hand-checked cases.

Каждый ожидаемый результат выведен вручную из правил
``kg_retrievers.gap_missing_regime``: a Measurement is a gap iff it has **no**
``ABOUT_REGIME`` / ``PROCESSED_BY`` path to a ``ProcessingRegime`` (directly or via
its ``Sample`` / ``Experiment`` owner). ``subject_id`` comes from ``ABOUT_MATERIAL``
(else empty string), ``property_id`` from ``OF_PROPERTY`` (else ``None``).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.gap_missing_regime import (
    MissingRegimeGap,
    _measurements_with_regime,
    find_missing_regime_gaps,
)
from kg_retrievers.graph_store import KuzuGraphStore


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _meas(store: KuzuGraphStore, mid: str, value: float = 42.0) -> None:
    store.upsert_node(
        mid, "Measurement", property_name="recovery", value_normalized=value, normalized_unit="pct"
    )


def _regime(store: KuzuGraphStore, rid: str) -> None:
    store.upsert_node(rid, "ProcessingRegime", name=rid)


def test_one_gap_for_regimeless_measurement(store: KuzuGraphStore) -> None:
    # m_wired -> ABOUT_REGIME -> reg ; m_bare has a value but no regime.
    _meas(store, "m_wired")
    _meas(store, "m_bare")
    _regime(store, "reg1")
    store.upsert_edge("m_wired", "reg1", "ABOUT_REGIME")

    gaps = find_missing_regime_gaps(store)
    # (1) exactly one gap; (2) it is the regime-less measurement, not the wired one.
    assert len(gaps) == 1
    assert gaps[0].measurement_id == "m_bare"
    assert {g.measurement_id for g in gaps} == {"m_bare"}


def test_subtype_and_as_dict_payload(store: KuzuGraphStore) -> None:
    _meas(store, "m_bare")
    store.upsert_node("mat1", "Material", name="pyrite")
    store.upsert_node("prop1", "Property", name="recovery")
    store.upsert_edge("m_bare", "mat1", "ABOUT_MATERIAL")
    store.upsert_edge("m_bare", "prop1", "OF_PROPERTY")

    gaps = find_missing_regime_gaps(store)
    assert len(gaps) == 1
    g = gaps[0]
    # (3) subtype fixed on every result.
    assert all(x.subtype == "missing_regime" for x in gaps)
    assert g.subtype == "missing_regime"
    # (4) as_dict carries all four fields with the wired subject/property.
    d = g.as_dict()
    assert d == {
        "measurement_id": "m_bare",
        "subject_id": "mat1",
        "property_id": "prop1",
        "subtype": "missing_regime",
    }
    assert set(d) == {"measurement_id", "subject_id", "property_id", "subtype"}


def test_all_measurements_have_regime_returns_empty(store: KuzuGraphStore) -> None:
    # Direct ABOUT_REGIME on one, owner PROCESSED_BY path on the other -> no gaps.
    _meas(store, "m_direct")
    _meas(store, "m_owned")
    _regime(store, "reg1")
    _regime(store, "reg2")
    store.upsert_edge("m_direct", "reg1", "ABOUT_REGIME")
    # m_owned <- sample -> PROCESSED_BY -> reg2 (owner hop).
    store.upsert_node("s1", "Sample", name="s1")
    store.upsert_edge("m_owned", "s1", "FROM_SAMPLE")
    store.upsert_edge("s1", "reg2", "PROCESSED_BY")

    assert find_missing_regime_gaps(store) == []
    assert _measurements_with_regime(store) == {"m_direct", "m_owned"}


def test_results_sorted_by_measurement_id(store: KuzuGraphStore) -> None:
    for mid in ("m_c", "m_a", "m_b"):
        _meas(store, mid)
    gaps = find_missing_regime_gaps(store)
    ids = [g.measurement_id for g in gaps]
    # (6) deterministic ascending order regardless of insertion order.
    assert ids == ["m_a", "m_b", "m_c"] == sorted(ids)


def test_empty_store_returns_empty(store: KuzuGraphStore) -> None:
    # (7) no nodes -> no gaps, and no regime-covered measurements.
    assert find_missing_regime_gaps(store) == []
    assert _measurements_with_regime(store) == set()


def test_subject_empty_string_when_no_material_edge(store: KuzuGraphStore) -> None:
    # (8) subject_id defaults to "" when the ABOUT_MATERIAL edge is absent;
    # property_id defaults to None when there is no OF_PROPERTY edge.
    _meas(store, "m_bare")
    gaps = find_missing_regime_gaps(store)
    assert len(gaps) == 1
    assert isinstance(gaps[0], MissingRegimeGap)
    assert gaps[0].subject_id == ""
    assert gaps[0].property_id is None


def test_owner_hop_alone_covers_measurement(store: KuzuGraphStore) -> None:
    # A measurement with only the owner PROCESSED_BY path is covered (not a gap).
    _meas(store, "m_owned")
    _meas(store, "m_bare")
    _regime(store, "reg1")
    store.upsert_node("exp1", "Experiment", name="exp1")
    store.upsert_edge("m_owned", "exp1", "MEASURED_IN")
    store.upsert_edge("exp1", "reg1", "PROCESSED_BY")

    gaps = find_missing_regime_gaps(store)
    assert [g.measurement_id for g in gaps] == ["m_bare"]
