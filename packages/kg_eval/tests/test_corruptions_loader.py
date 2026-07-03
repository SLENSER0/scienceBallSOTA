"""[DE] Corruption operator + isolated loader (§33.3/§33.6, D10/D11)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_eval.datasets.corruptions import OPERATOR_CATALOG, retract_cells
from kg_eval.datasets.loader import load_synthetic
from kg_eval.datasets.synthetic import build_synthetic
from kg_retrievers.absence_signals import GENUINE_GAP, PRESENT, RETRACTED, classify_cell
from kg_retrievers.graph_store import KuzuGraphStore


def test_retract_cells_flips_present_to_retracted() -> None:
    store = KuzuGraphStore(str(Path(tempfile.mkdtemp()) / "g"))
    try:
        m = build_synthetic(store)
        present_cell = next(c for c in m.cells if c.archetype == "PRESENT_TABLE")
        # before corruption: a present cell
        assert (
            classify_cell(store, present_cell.material_id, present_cell.property_id).verdict
            == PRESENT
        )
        recs = retract_cells(store, m, archetype="PRESENT_TABLE")
        assert recs and all(r["ok"] for r in recs)
        # after: the same cell reads retracted, not a gap
        after = classify_cell(store, present_cell.material_id, present_cell.property_id).verdict
        assert after == RETRACTED
    finally:
        store.close()


def test_retract_cells_default_is_idempotent_on_seeded_retractions() -> None:
    store = KuzuGraphStore(str(Path(tempfile.mkdtemp()) / "g"))
    try:
        m = build_synthetic(store)  # RETRACTED cells already retracted at build
        retract_cells(store, m)  # re-retract → no-op
        for c in m.cells:
            if c.archetype == "RETRACTED":
                assert classify_cell(store, c.material_id, c.property_id).verdict == RETRACTED
    finally:
        store.close()


def test_operator_catalog_declares_the_slice() -> None:
    assert "retract_cells" in OPERATOR_CATALOG
    assert len(OPERATOR_CATALOG) == 10  # one implemented + nine spec-only


def test_loader_isolation_and_provenance() -> None:
    ctx = load_synthetic()
    tmp = ctx._tmp_dir
    try:
        assert Path(str(tmp)).exists()
        assert ctx.provenance["backend"] == "embedded"
        assert ctx.provenance["seed"] == 20260701
        assert ctx.provenance["thresholds"]["possible_miss_at"] == 0.60
        # the store is live and classifiable
        gg = next(c for c in ctx.manifest.cells if c.archetype == "FALSE_MISS")
        assert (
            classify_cell(ctx.store, gg.material_id, gg.property_id, value_gate=True).verdict
            == GENUINE_GAP
        )
    finally:
        ctx.close()
        assert not Path(str(tmp)).exists()  # temp dir removed
        ctx.close()  # safe to close twice


def test_loader_rejects_unknown_profile() -> None:
    with pytest.raises(ValueError, match="profile"):
        load_synthetic(profile="cached-llm")


def test_loader_is_deterministic() -> None:
    with load_synthetic(n_materials=6) as a, load_synthetic(n_materials=6) as b:
        assert a.manifest.to_dict() == b.manifest.to_dict()
