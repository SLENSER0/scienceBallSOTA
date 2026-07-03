"""[DE] Confidence-of-absence opt-in flags + N1 honest committed cap (§33/N1-N3, D14/D15)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_common.config import Settings
from kg_retrievers.absence_annotate import annotate_gaps
from kg_retrievers.absence_signals import GENUINE_GAP, POSSIBLE_MISS
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.recall_priors import smoothed_recall


def test_flags_default_off_and_committed_mapping(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    s = Settings()
    assert s.honest_recall_priors is False
    assert s.absence_value_gate is False
    assert s.prose_observation_extraction is False
    # N1 mapping: default → legacy (None); honest on → committed floor (False), never True.
    assert s.prose_observations_committed() is None
    monkeypatch.setenv("MKG_HONEST_RECALL_PRIORS", "true")
    assert Settings().prose_observations_committed() is False


def test_committed_recall_cap_lowers_overstated_recall() -> None:
    # a high empirical hit-rate (candidates proposed) overstates committed recall.
    uncapped = smoothed_recall(90, 100)  # ≈ 0.75
    capped = smoothed_recall(90, 100, committed_recall_cap=0.15)
    assert uncapped > 0.5
    assert capped == 0.15  # clamped from above to the honest floor
    # the cap never raises a low estimate
    assert smoothed_recall(1, 100, committed_recall_cap=0.15) < 0.15


def test_annotate_gaps_resolves_value_gate_from_config(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    store = KuzuGraphStore(str(Path(tempfile.mkdtemp()) / "g"))
    try:
        from kg_common import make_id

        mat = make_id("Material", "flag alloy")
        prop = make_id("Property", "flag prop")
        doc = make_id("Document", "flag doc")
        chunk = make_id("Chunk", "flag chunk")
        store.upsert_node(mat, "Material", name="alloy")
        store.upsert_node(prop, "Property", property_name="flag_prop", name="Flag")
        store.upsert_node(doc, "Document", name="Doc")
        store.upsert_node(chunk, "Chunk", text="alloy prose")
        store.upsert_edge(doc, chunk, "HAS_CHUNK")
        store.upsert_edge(chunk, mat, "MENTIONS")
        store.upsert_edge(chunk, prop, "MENTIONS", value_present=False)  # named, no value
        gaps = [{"material_id": mat, "property_id": prop, "gap_id": "g"}]

        # config default (flag off) → possible_miss (gate not applied)
        (off,) = annotate_gaps(store, gaps)
        assert off.verdict == POSSIBLE_MISS

        # flip the config flag ON → annotate_gaps resolves value_gate from config
        import kg_common.config as cfg

        cfg.get_settings.cache_clear()
        monkeypatch.setenv("MKG_ABSENCE_VALUE_GATE", "true")
        try:
            (on,) = annotate_gaps(store, gaps)
            assert on.verdict == GENUINE_GAP
        finally:
            cfg.get_settings.cache_clear()
    finally:
        store.close()
