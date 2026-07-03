"""[DE] Opt-in absence value gate (§33/N2, D3).

The mentioned-but-unmeasured branch of :func:`classify_cell` forces
``possible_miss`` — it cannot tell *a property being named* from *a value being
stated*. The opt-in value gate reads the ``value_present`` flag (D1/D2) on the
prose MENTIONS edge and downgrades ``possible_miss`` → ``genuine_gap`` **only** on
complete positive evidence of no value:

    Document(doc)-HAS_CHUNK->Chunk(c)-MENTIONS->{material, P_true, P_false, P_unk}

- ``P_true``  — prose states a value (value_present=True)  → stays possible_miss
  (TRUE_MISS: a real datum the offline extractor missed);
- ``P_false`` — prose only names it   (value_present=False) → genuine_gap
  (FALSE_MISS: property named, never measured — the discriminator);
- ``P_unk``   — structural mention    (value_present unset) → stays possible_miss
  ("do not downgrade on unknown");
- gate OFF → all three stay possible_miss (baseline pins are unchanged).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.absence_annotate import annotate_gaps
from kg_retrievers.absence_signals import GENUINE_GAP, POSSIBLE_MISS, classify_cell
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.mentions_lineage import mention_value_status

DOC = make_id("Document", "vg doc")
CHUNK = make_id("Chunk", "vg chunk")
MAT = make_id("Material", "vg alloy")
P_TRUE = make_id("Property", "hardness")  # prose states a value
P_FALSE = make_id("Property", "elongation")  # prose only names it
P_UNK = make_id("Property", "modulus")  # structural mention, no flag


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    s = KuzuGraphStore(str(Path(tempfile.mkdtemp()) / "g"))
    s.upsert_node(DOC, "Document", name="Doc")
    s.upsert_node(CHUNK, "Chunk", text="alloy prose")
    s.upsert_node(MAT, "Material", name="alloy")
    s.upsert_node(P_TRUE, "Property", property_name="hardness", name="Hardness")
    s.upsert_node(P_FALSE, "Property", property_name="elongation", name="Elongation")
    s.upsert_node(P_UNK, "Property", property_name="modulus", name="Modulus")
    s.upsert_edge(DOC, CHUNK, "HAS_CHUNK")
    s.upsert_edge(CHUNK, MAT, "MENTIONS")  # material edge: no value flag
    s.upsert_edge(CHUNK, P_TRUE, "MENTIONS", value_present=True)
    s.upsert_edge(CHUNK, P_FALSE, "MENTIONS", value_present=False)
    s.upsert_edge(CHUNK, P_UNK, "MENTIONS")  # structural: value_present NULL
    yield s
    s.close()


# -- the raw three-valued signal -------------------------------------------
def test_mention_value_status_three_valued(store: KuzuGraphStore) -> None:
    assert mention_value_status(store, MAT, P_TRUE) is True
    assert mention_value_status(store, MAT, P_FALSE) is False
    assert mention_value_status(store, MAT, P_UNK) is None
    # material not mentioned anywhere → unknown, never False
    assert mention_value_status(store, make_id("Material", "ghost"), P_FALSE) is None


# -- gate OFF: baseline unchanged (all mentioned-miss → possible_miss) ------
def test_gate_off_all_possible_miss(store: KuzuGraphStore) -> None:
    for pid in (P_TRUE, P_FALSE, P_UNK):
        sig = classify_cell(store, MAT, pid)
        assert sig.verdict == POSSIBLE_MISS
        assert "mention_value_present" not in sig.signals  # gate never ran


# -- gate ON: the discriminator --------------------------------------------
def test_gate_on_true_miss_stays_possible_miss(store: KuzuGraphStore) -> None:
    sig = classify_cell(store, MAT, P_TRUE, value_gate=True)
    assert sig.verdict == POSSIBLE_MISS
    assert sig.signals["mention_value_present"] is True


def test_gate_on_false_miss_downgrades_to_genuine_gap(store: KuzuGraphStore) -> None:
    sig = classify_cell(store, MAT, P_FALSE, value_gate=True)
    assert sig.verdict == GENUINE_GAP
    assert sig.signals["mention_value_present"] is False
    # posterior is consistent with the verdict: P(missed) is now low.
    assert sig.p_extractor_missed <= 0.25 < sig.p_truly_absent


def test_gate_on_unknown_flag_does_not_downgrade(store: KuzuGraphStore) -> None:
    # a structural mention (no value_present) is NOT complete positive evidence.
    sig = classify_cell(store, MAT, P_UNK, value_gate=True)
    assert sig.verdict == POSSIBLE_MISS
    assert sig.signals["mention_value_present"] is None


# -- gate does not touch empty / unmentioned cells -------------------------
def test_gate_ignores_unmentioned_cell(store: KuzuGraphStore) -> None:
    # a material never mentioned + never measured is decided by the recall prior,
    # not the value gate — turning the gate on must not change that.
    ghost = make_id("Material", "unmentioned")
    off = classify_cell(store, ghost, P_TRUE, recall_prior=0.1)
    on = classify_cell(store, ghost, P_TRUE, recall_prior=0.1, value_gate=True)
    assert off.verdict == on.verdict == GENUINE_GAP
    assert "mention_value_present" not in on.signals


# -- threads through annotate_gaps -----------------------------------------
def test_annotate_gaps_forwards_value_gate(store: KuzuGraphStore) -> None:
    gaps = [
        {"material_id": MAT, "property_id": P_FALSE, "gap_id": "g_false"},
        {"material_id": MAT, "property_id": P_TRUE, "gap_id": "g_true"},
    ]
    off = {a.gap_id: a.verdict for a in annotate_gaps(store, gaps)}
    on = {a.gap_id: a.verdict for a in annotate_gaps(store, gaps, value_gate=True)}
    assert off == {"g_false": POSSIBLE_MISS, "g_true": POSSIBLE_MISS}
    assert on == {"g_false": GENUINE_GAP, "g_true": POSSIBLE_MISS}
