"""Regime-aware contradiction detection — hand-checked cases (§15.4).

Every expected value is worked out by hand from the rules in
``kg_retrievers.contradiction_regime``:
- numeric relative divergence ``|a-b| / max(|a|,|b|)`` vs ``min_divergence``;
- a contradiction fires only inside one ``(subject, property, ProcessingRegime)``
  group and only when the confidence intervals are disjoint.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.contradiction_regime import ContradictionPair, find_contradictions
from kg_retrievers.graph_store import KuzuGraphStore


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _meas(store: KuzuGraphStore, mid: str, value: float, **props: object) -> None:
    store.upsert_node(
        mid,
        "Measurement",
        property_name="recovery",
        value_normalized=value,
        normalized_unit="pct",
        **props,
    )


def _wire(store: KuzuGraphStore, mid: str, subject: str, regime: str) -> None:
    store.upsert_edge(mid, subject, "ABOUT_MATERIAL")
    store.upsert_edge(mid, regime, "ABOUT_REGIME")


def _fixture_same_regime(store: KuzuGraphStore) -> None:
    """One material, one regime, two divergent measurements with disjoint CIs."""
    store.upsert_node("material:cu", "Material", name="Медь")
    store.upsert_node("regime:leach-a", "ProcessingRegime", name="выщелачивание A")
    # |100-60| / 100 = 0.40 >= 0.30; CIs [95,105] vs [50,70] are disjoint.
    _meas(store, "meas:a", 100.0, ci_low=95.0, ci_high=105.0, evidence_ids=["ev:a"])
    _meas(store, "meas:b", 60.0, ci_low=50.0, ci_high=70.0, evidence_ids=["ev:b"])
    _wire(store, "meas:a", "material:cu", "regime:leach-a")
    _wire(store, "meas:b", "material:cu", "regime:leach-a")


def test_same_regime_divergent_disjoint_ci_is_one_pair(store: KuzuGraphStore) -> None:
    _fixture_same_regime(store)
    pairs = find_contradictions(store)
    assert len(pairs) == 1
    p = pairs[0]
    assert (p.measurement_a, p.measurement_b) == ("meas:a", "meas:b")
    assert p.subject == "material:cu"
    assert p.property == "recovery"
    assert p.regime == "regime:leach-a"
    assert abs(p.divergence - 0.40) < 1e-9
    assert p.ci_overlap is False


def test_different_regime_is_no_contradiction(store: KuzuGraphStore) -> None:
    # Acceptance: SAME subject + property, DIFFERENT ProcessingRegime → 0 pairs,
    # even though 100 vs 60 diverges by 0.40 — different regimes are not comparable.
    store.upsert_node("material:cu", "Material", name="Медь")
    store.upsert_node("regime:leach-a", "ProcessingRegime", name="выщелачивание A")
    store.upsert_node("regime:leach-b", "ProcessingRegime", name="выщелачивание B")
    _meas(store, "meas:a", 100.0, ci_low=95.0, ci_high=105.0)
    _meas(store, "meas:b", 60.0, ci_low=50.0, ci_high=70.0)
    _wire(store, "meas:a", "material:cu", "regime:leach-a")
    _wire(store, "meas:b", "material:cu", "regime:leach-b")
    assert find_contradictions(store) == []


def test_overlapping_ci_is_no_contradiction(store: KuzuGraphStore) -> None:
    # Acceptance: divergence 0.40 >= 0.30 but the CIs [50,120] & [40,110] overlap
    # (50 <= 110) → the uncertainty bands agree → 0 pairs.
    store.upsert_node("material:cu", "Material", name="Медь")
    store.upsert_node("regime:leach-a", "ProcessingRegime", name="выщелачивание A")
    _meas(store, "meas:a", 100.0, ci_low=50.0, ci_high=120.0)
    _meas(store, "meas:b", 60.0, ci_low=40.0, ci_high=110.0)
    _wire(store, "meas:a", "material:cu", "regime:leach-a")
    _wire(store, "meas:b", "material:cu", "regime:leach-a")
    assert find_contradictions(store) == []


def test_close_values_below_threshold_is_no_contradiction(store: KuzuGraphStore) -> None:
    # |100-90| / 100 = 0.10 < 0.30 → the values agree, no contradiction (no CI set).
    store.upsert_node("material:cu", "Material", name="Медь")
    store.upsert_node("regime:leach-a", "ProcessingRegime", name="выщелачивание A")
    _meas(store, "meas:a", 100.0)
    _meas(store, "meas:b", 90.0)
    _wire(store, "meas:a", "material:cu", "regime:leach-a")
    _wire(store, "meas:b", "material:cu", "regime:leach-a")
    assert find_contradictions(store) == []


def test_min_divergence_is_configurable(store: KuzuGraphStore) -> None:
    # |100-80| / 100 = 0.20: below the 0.30 default, above a 0.15 override. No CIs
    # → nothing to overlap, so the override alone decides.
    store.upsert_node("material:cu", "Material", name="Медь")
    store.upsert_node("regime:leach-a", "ProcessingRegime", name="выщелачивание A")
    _meas(store, "meas:a", 100.0)
    _meas(store, "meas:b", 80.0)
    _wire(store, "meas:a", "material:cu", "regime:leach-a")
    _wire(store, "meas:b", "material:cu", "regime:leach-a")
    assert find_contradictions(store) == []
    loose = find_contradictions(store, min_divergence=0.15)
    assert len(loose) == 1
    assert abs(loose[0].divergence - 0.20) < 1e-9


def test_evidence_ids_are_populated(store: KuzuGraphStore) -> None:
    _fixture_same_regime(store)
    p = find_contradictions(store)[0]
    # Both sides' ``evidence_ids`` props are merged, deduped and sorted.
    assert p.evidence_ids == ("ev:a", "ev:b")


def test_evidence_ids_include_linked_evidence_nodes(store: KuzuGraphStore) -> None:
    # Evidence supplied as graph nodes (not props) is gathered via the edge too.
    store.upsert_node("material:cu", "Material", name="Медь")
    store.upsert_node("regime:leach-a", "ProcessingRegime", name="выщелачивание A")
    _meas(store, "meas:a", 100.0)
    _meas(store, "meas:b", 60.0)
    _wire(store, "meas:a", "material:cu", "regime:leach-a")
    _wire(store, "meas:b", "material:cu", "regime:leach-a")
    store.upsert_node("ev:node1", "Evidence", text="цитата 1")
    store.upsert_edge("meas:a", "ev:node1", "SUPPORTED_BY")
    p = find_contradictions(store)[0]
    assert "ev:node1" in p.evidence_ids


def test_multiple_groups_are_isolated(store: KuzuGraphStore) -> None:
    # Two independent (subject, property, regime) groups, each with its own
    # contradiction — they must not cross-contaminate.
    store.upsert_node("material:cu", "Material", name="Медь")
    store.upsert_node("material:ni", "Material", name="Никель")
    store.upsert_node("regime:leach-a", "ProcessingRegime", name="выщелачивание A")
    store.upsert_node("regime:leach-b", "ProcessingRegime", name="выщелачивание B")
    _meas(store, "meas:cu1", 100.0)
    _meas(store, "meas:cu2", 60.0)
    _meas(store, "meas:ni1", 90.0)
    _meas(store, "meas:ni2", 40.0)
    _wire(store, "meas:cu1", "material:cu", "regime:leach-a")
    _wire(store, "meas:cu2", "material:cu", "regime:leach-a")
    _wire(store, "meas:ni1", "material:ni", "regime:leach-b")
    _wire(store, "meas:ni2", "material:ni", "regime:leach-b")
    pairs = find_contradictions(store)
    assert len(pairs) == 2
    by_subject = {p.subject: p for p in pairs}
    assert set(by_subject) == {"material:cu", "material:ni"}
    assert (by_subject["material:cu"].measurement_a, by_subject["material:cu"].measurement_b) == (
        "meas:cu1",
        "meas:cu2",
    )
    assert by_subject["material:ni"].regime == "regime:leach-b"


def test_as_dict_shape(store: KuzuGraphStore) -> None:
    _fixture_same_regime(store)
    p = find_contradictions(store)[0]
    assert isinstance(p, ContradictionPair)
    d = p.as_dict()
    assert set(d) == {
        "measurement_a",
        "measurement_b",
        "subject",
        "property",
        "regime",
        "divergence",
        "ci_overlap",
        "evidence_ids",
    }
    assert d["subject"] == "material:cu"
    assert d["regime"] == "regime:leach-a"
    assert d["property"] == "recovery"
    assert d["ci_overlap"] is False
    assert isinstance(d["evidence_ids"], list)
    assert d["evidence_ids"] == ["ev:a", "ev:b"]
