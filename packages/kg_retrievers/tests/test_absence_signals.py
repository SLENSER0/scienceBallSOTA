"""Fused three-signal absence verdict over a hand-built graph (§25.11).

Builds a tiny fixture that exercises every branch of :func:`classify_cell` on a
single property (``recovery``), with hand-checked expectations:

    Measurement(m_ni, value=92.0) -ABOUT_MATERIAL-> nickel     (active, valued)
    Measurement(m_co, no value)   -ABOUT_MATERIAL-> cobalt     (active, valueless)
    Measurement(m_fe, value=80.0) -ABOUT_MATERIAL-> iron       (retracted)
    Document(doc1)-HAS_CHUNK->Chunk(c1)-MENTIONS-> copper      (mentioned, unmeasured)
    zinc                                                        (empty, unmentioned)

- nickel has an active valued measurement of recovery -> ``present``;
- cobalt's active measurement of recovery carries no value -> ``covered``;
- iron's only recovery measurement is retracted -> ``retracted`` (NOT covered);
- copper is mentioned but never measured -> ``possible_miss``;
- zinc is empty + unmentioned -> Bayesian on ``recall_prior``:
    low prior 0.1  -> P(missed)=0.0323 -> ``genuine_gap``;
    high prior 0.9 -> P(missed)=0.7297 -> ``possible_miss``;
    default 0.55   -> P(missed)=0.2683 -> ``abstain``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.absence_signals import (
    AbsenceSignal,
    classify_cell,
)
from kg_retrievers.graph_store import KuzuGraphStore

DOC1 = make_id("Document", "doc one")
C1 = make_id("Chunk", "chunk one")
NICKEL = make_id("Material", "nickel")
COBALT = make_id("Material", "cobalt")
IRON = make_id("Material", "iron")
COPPER = make_id("Material", "copper")
ZINC = make_id("Material", "zinc")
PROP_RECOVERY = make_id("Property", "recovery")

M_NI = make_id("Measurement", "nickel recovery")
M_CO = make_id("Measurement", "cobalt recovery valueless")
M_FE = make_id("Measurement", "iron recovery retracted")


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _build(s)
    yield s
    s.close()


def _build(s: KuzuGraphStore) -> None:
    """One material per branch of classify_cell, all on the 'recovery' property."""
    s.upsert_node(PROP_RECOVERY, "Property", property_name="recovery", name="Recovery")
    for mid, name in (
        (NICKEL, "nickel"),
        (COBALT, "cobalt"),
        (IRON, "iron"),
        (COPPER, "copper"),
        (ZINC, "zinc"),
    ):
        s.upsert_node(mid, "Material", name=name, domain="hydrometallurgy")

    # nickel: active measurement WITH a numeric value -> present.
    s.upsert_node(M_NI, "Measurement", property_name="recovery", value_normalized=92.0)
    s.upsert_edge(M_NI, NICKEL, "ABOUT_MATERIAL", confidence=0.9)

    # cobalt: active measurement of recovery but NO value -> covered.
    s.upsert_node(M_CO, "Measurement", property_name="recovery")
    s.upsert_edge(M_CO, COBALT, "ABOUT_MATERIAL", confidence=0.8)

    # iron: a recovery measurement that we then soft-retract -> retracted.
    s.upsert_node(M_FE, "Measurement", property_name="recovery", value_normalized=80.0)
    s.upsert_edge(M_FE, IRON, "ABOUT_MATERIAL", confidence=0.7)

    # copper: mentioned in a document but never measured -> possible_miss.
    s.upsert_node(DOC1, "Document", name="Doc One")
    s.upsert_node(C1, "Chunk", text="copper leaching")
    s.upsert_edge(DOC1, C1, "HAS_CHUNK")
    s.upsert_edge(C1, COPPER, "MENTIONS")

    # zinc: bare material, no measurement, no mention -> Bayesian branch.


def _retract_iron(s: KuzuGraphStore) -> None:
    from kg_retrievers.retractions import retract

    retract(s, M_FE, reason="bad calibration", actor="alice", at="2026-07-03")


# -- signal 1: active observation -> present / covered ---------------------
def test_active_valued_measurement_is_present(store: KuzuGraphStore) -> None:
    sig = classify_cell(store, NICKEL, PROP_RECOVERY)
    assert isinstance(sig, AbsenceSignal)
    assert sig.verdict == "present"
    assert sig.p_truly_absent == 0.0
    assert sig.p_extractor_missed == 0.0
    assert sig.signals["active_observations"] == 1
    assert sig.signals["retracted_observations"] == 0
    assert sig.signals["mentioned_without_observation"] is False


def test_active_valueless_measurement_is_covered(store: KuzuGraphStore) -> None:
    # An active observation exists for recovery but carries no numeric value.
    sig = classify_cell(store, COBALT, "recovery")
    assert sig.verdict == "covered"
    assert sig.signals["active_observations"] == 1
    assert sig.p_truly_absent == 0.0


# -- signal 2: retracted-only cell -> retracted (NOT covered) --------------
def test_retracted_only_cell_is_retracted_not_covered(store: KuzuGraphStore) -> None:
    _retract_iron(store)
    sig = classify_cell(store, IRON, PROP_RECOVERY)
    assert sig.verdict == "retracted"
    assert sig.verdict != "covered"  # §25.12: must not be counted as coverage
    assert sig.signals["active_observations"] == 0
    assert sig.signals["retracted_observations"] == 1


# -- signal 3: mentioned but never measured -> possible_miss ---------------
def test_mentioned_without_observation_is_possible_miss(store: KuzuGraphStore) -> None:
    sig = classify_cell(store, COPPER, PROP_RECOVERY)
    assert sig.verdict == "possible_miss"
    assert sig.signals["mentioned_without_observation"] is True
    assert sig.signals["active_observations"] == 0
    # A mention makes existence near-certain -> P(missed) crosses the threshold.
    assert sig.p_extractor_missed >= 0.60
    assert sig.p_extractor_missed == pytest.approx(0.7297, abs=1e-4)
    assert sig.p_truly_absent == pytest.approx(0.2703, abs=1e-4)


# -- Bayesian branch: empty + LOW recall prior -> genuine_gap --------------
def test_empty_low_recall_prior_is_genuine_gap(store: KuzuGraphStore) -> None:
    sig = classify_cell(store, ZINC, "recovery", recall_prior=0.1)
    assert sig.verdict == "genuine_gap"
    # π=0.1, r=0.7 -> P(missed)=0.03/0.93=0.0323, P(absent)=0.9/0.93=0.9677.
    assert sig.p_extractor_missed == pytest.approx(0.0323, abs=1e-4)
    assert sig.p_truly_absent == pytest.approx(0.9677, abs=1e-4)
    assert sig.p_extractor_missed <= 0.25


# -- Bayesian branch: empty + HIGH recall prior -> possible_miss -----------
def test_empty_high_recall_prior_is_possible_miss(store: KuzuGraphStore) -> None:
    sig = classify_cell(store, ZINC, "recovery", recall_prior=0.9)
    assert sig.verdict == "possible_miss"
    # π=0.9, r=0.7 -> P(missed)=0.27/0.37=0.7297.
    assert sig.p_extractor_missed == pytest.approx(0.7297, abs=1e-4)
    assert sig.p_extractor_missed >= 0.60


# -- Bayesian branch: empty + mid (default) recall prior -> abstain --------
def test_empty_default_recall_prior_abstains(store: KuzuGraphStore) -> None:
    sig = classify_cell(store, ZINC, "recovery")  # default recall_prior=0.55
    assert sig.verdict == "abstain"
    # π=0.55, r=0.7 -> P(missed)=0.165/0.615=0.2683, strictly between the two gates.
    assert sig.p_extractor_missed == pytest.approx(0.2683, abs=1e-4)
    assert 0.25 < sig.p_extractor_missed < 0.60


# -- as_dict is a faithful, plain-dict projection --------------------------
def test_as_dict_round_trips(store: KuzuGraphStore) -> None:
    sig = classify_cell(store, ZINC, "recovery", recall_prior=0.9)
    d = sig.as_dict()
    assert set(d) == {"verdict", "p_truly_absent", "p_extractor_missed", "signals"}
    assert d["verdict"] == "possible_miss"
    assert d["p_extractor_missed"] == sig.p_extractor_missed
    assert d["signals"]["recall_prior"] == 0.9
    assert set(d["signals"]) == {
        "active_observations",
        "retracted_observations",
        "mentioned_without_observation",
        "recall_prior",
    }
    # as_dict copies the signals dict rather than aliasing the frozen one.
    d["signals"]["recall_prior"] = 0.0
    assert sig.signals["recall_prior"] == 0.9


# -- probability fields stay in the unit interval across every verdict -----
def test_probability_fields_in_unit_interval(store: KuzuGraphStore) -> None:
    _retract_iron(store)
    cells = [
        classify_cell(store, NICKEL, PROP_RECOVERY),  # present
        classify_cell(store, COBALT, PROP_RECOVERY),  # covered
        classify_cell(store, IRON, PROP_RECOVERY),  # retracted
        classify_cell(store, COPPER, PROP_RECOVERY),  # possible_miss (mention)
        classify_cell(store, ZINC, "recovery", recall_prior=0.1),  # genuine_gap
        classify_cell(store, ZINC, "recovery", recall_prior=0.9),  # possible_miss
        classify_cell(store, ZINC, "recovery"),  # abstain
    ]
    for sig in cells:
        assert 0.0 <= sig.p_truly_absent <= 1.0
        assert 0.0 <= sig.p_extractor_missed <= 1.0
