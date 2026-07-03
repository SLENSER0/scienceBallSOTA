"""§25.13 — annotate gaps with an absence verdict over a hand-built graph.

Reuses the §25.11 fixture shape (one material per branch of ``classify_cell``,
all on the ``recovery`` property) and feeds each cell in as a *gap* to be
re-judged:

    Measurement(m_ni, value=92.0) -ABOUT_MATERIAL-> nickel   (active, valued)
    Measurement(m_co, no value)   -ABOUT_MATERIAL-> cobalt   (active, valueless)
    Measurement(m_fe, value=80.0) -ABOUT_MATERIAL-> iron     (retracted)
    Document(doc1)-HAS_CHUNK->Chunk(c1)-MENTIONS-> copper    (mentioned, unmeasured)
    zinc                                                      (empty, unmentioned)

Hand-checked outcomes:

- nickel gap  -> ``present``       (downgraded), p_truly_absent 0.0;
- cobalt gap  -> ``covered``       (downgraded), p_truly_absent 0.0;
- iron gap    -> ``retracted``     (§25.12),     p_truly_absent 0.0;
- copper gap  -> ``possible_miss`` (mention),    p_truly_absent 0.2703;
- zinc gap, recall_prior 0.1  -> ``genuine_gap``, p_truly_absent 0.9677;
- zinc gap, recall_prior 0.55 -> ``abstain``,     p_truly_absent 0.7317.

``filter_genuine`` keeps only ``genuine_gap`` / ``possible_miss``; every note is
a non-empty RU/EN string and every ``p_truly_absent`` stays in ``[0, 1]``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.absence_annotate import (
    AnnotatedGap,
    annotate_gaps,
    filter_genuine,
)
from kg_retrievers.graph_store import KuzuGraphStore

NICKEL = make_id("Material", "nickel")
COBALT = make_id("Material", "cobalt")
IRON = make_id("Material", "iron")
COPPER = make_id("Material", "copper")
ZINC = make_id("Material", "zinc")
PROP_RECOVERY = make_id("Property", "recovery")

DOC1 = make_id("Document", "doc one")
C1 = make_id("Chunk", "chunk one")
M_NI = make_id("Measurement", "nickel recovery")
M_CO = make_id("Measurement", "cobalt recovery valueless")
M_FE = make_id("Measurement", "iron recovery retracted")


def _gap(material_id: str, property_id: str = PROP_RECOVERY, gap_id: str | None = None) -> dict:
    """A minimal gap record: the (material, property) cell to be re-judged."""
    return {
        "gap_id": gap_id or make_id("Gap", f"{material_id}:{property_id}"),
        "material_id": material_id,
        "property_id": property_id,
    }


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


def _has_cyrillic(text: str) -> bool:
    return any("Ѐ" <= ch <= "ӿ" for ch in text)


# -- empty cell -> genuine_gap (low prior) --------------------------------
def test_empty_cell_low_prior_is_genuine_gap(store: KuzuGraphStore) -> None:
    (ann,) = annotate_gaps(store, [_gap(ZINC)], recall_prior=0.1)
    assert isinstance(ann, AnnotatedGap)
    assert ann.verdict == "genuine_gap"
    assert ann.material_id == ZINC
    assert ann.property_id == PROP_RECOVERY
    # π=0.1, r=0.7 -> P(absent)=0.9/0.93=0.9677.
    assert ann.p_truly_absent == pytest.approx(0.9677, abs=1e-4)
    assert ann.is_genuine is True


# -- empty cell -> abstain (default prior) --------------------------------
def test_empty_cell_default_prior_abstains(store: KuzuGraphStore) -> None:
    (ann,) = annotate_gaps(store, [_gap(ZINC)])  # default recall_prior=0.55
    assert ann.verdict == "abstain"
    # π=0.55, r=0.7 -> P(absent)=0.45/0.615=0.7317.
    assert ann.p_truly_absent == pytest.approx(0.7317, abs=1e-4)
    assert ann.is_genuine is False


# -- measured cell -> present, downgraded ---------------------------------
def test_measured_cell_is_downgraded_present(store: KuzuGraphStore) -> None:
    (ann,) = annotate_gaps(store, [_gap(NICKEL)])
    assert ann.verdict == "present"
    assert ann.p_truly_absent == 0.0
    assert "downgraded" in ann.note
    assert ann.is_genuine is False


# -- valueless observation -> covered, downgraded -------------------------
def test_valueless_cell_is_downgraded_covered(store: KuzuGraphStore) -> None:
    (ann,) = annotate_gaps(store, [_gap(COBALT)])
    assert ann.verdict == "covered"
    assert ann.p_truly_absent == 0.0


# -- retracted-only cell -> retracted (NOT covered) -----------------------
def test_retracted_only_cell_is_retracted(store: KuzuGraphStore) -> None:
    _retract_iron(store)
    (ann,) = annotate_gaps(store, [_gap(IRON)])
    assert ann.verdict == "retracted"
    assert ann.verdict != "covered"  # §25.12: never counted as coverage
    assert ann.p_truly_absent == 0.0
    assert "§25.12" in ann.note


# -- every note is a non-empty RU string ----------------------------------
def test_notes_are_non_empty_russian(store: KuzuGraphStore) -> None:
    _retract_iron(store)
    gaps = [_gap(m) for m in (NICKEL, COBALT, IRON, COPPER, ZINC)]
    for ann in annotate_gaps(store, gaps, recall_prior=0.1):
        assert ann.note.strip()  # non-empty
        assert _has_cyrillic(ann.note)  # carries the RU note


# -- filter_genuine keeps genuine_gap / possible_miss, drops the rest -----
def test_filter_genuine_drops_covered_and_present(store: KuzuGraphStore) -> None:
    gaps = [_gap(NICKEL), _gap(COBALT), _gap(COPPER), _gap(ZINC)]
    annotated = annotate_gaps(store, gaps, recall_prior=0.1)
    verdicts = [a.verdict for a in annotated]
    assert verdicts == ["present", "covered", "possible_miss", "genuine_gap"]

    kept = filter_genuine(annotated)
    kept_verdicts = {a.verdict for a in kept}
    assert kept_verdicts == {"possible_miss", "genuine_gap"}
    assert "covered" not in kept_verdicts  # covered is dropped
    assert "present" not in kept_verdicts
    assert {a.material_id for a in kept} == {COPPER, ZINC}


# -- p_truly_absent stays in the unit interval across every verdict -------
def test_p_truly_absent_in_unit_interval(store: KuzuGraphStore) -> None:
    _retract_iron(store)
    gaps = [_gap(m) for m in (NICKEL, COBALT, IRON, COPPER, ZINC)]
    for ann in annotate_gaps(store, gaps):
        assert 0.0 <= ann.p_truly_absent <= 1.0


# -- possible_miss from a mention carries the classifier's posterior ------
def test_mentioned_cell_is_possible_miss(store: KuzuGraphStore) -> None:
    (ann,) = annotate_gaps(store, [_gap(COPPER)])
    assert ann.verdict == "possible_miss"
    assert ann.p_truly_absent == pytest.approx(0.2703, abs=1e-4)
    assert ann.is_genuine is True


# -- as_dict is a faithful, plain-dict projection -------------------------
def test_as_dict_projection(store: KuzuGraphStore) -> None:
    gid = make_id("Gap", "explicit gap id")
    (ann,) = annotate_gaps(store, [_gap(ZINC, gap_id=gid)], recall_prior=0.1)
    d = ann.as_dict()
    assert d == {
        "gap_id": gid,
        "material_id": ZINC,
        "property_id": PROP_RECOVERY,
        "verdict": "genuine_gap",
        "p_truly_absent": pytest.approx(0.9677, abs=1e-4),
        "note": ann.note,
    }
    assert set(d) == {"gap_id", "material_id", "property_id", "verdict", "p_truly_absent", "note"}
