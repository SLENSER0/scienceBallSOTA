"""Map of the unknown — absence-confidence aggregate (§25.11).

Hand-checkable over the seed graph. Recall of AbsenceAnalyzer's default extractor
is 0.7, so every empty (numeric) cell gets posterior 1/(2-0.7) ≈ 0.7692.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.absence_map import STATUSES, build_absence_map
from kg_retrievers.confidence_of_absence import (
    CONFIDENT_ABSENCE,
    COVERED,
    POSSIBLE_ABSENCE,
    UNKNOWN,
    ExtractorRecall,
)
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph

NICKEL = make_id("Material", "nickel")
WATER = make_id("Material", "mine water concentrator feed")

# posterior for an empty cell at the default recall 0.7 (see confidence_of_absence)
CONF_07 = round(1 / (2 - 0.7), 4)  # 0.7692


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(s)
    yield s
    s.close()


def test_map_has_cells_for_explicit_grid(store: KuzuGraphStore) -> None:
    # nickel × {recovery, flow_velocity}: recovery is a confident absence, but
    # flow_velocity is reachable (catholyte scheme) → COVERED (§25.11).
    m = build_absence_map(store, materials=[NICKEL], properties=["recovery", "flow_velocity"])
    assert len(m.cells) == 2
    assert m.summary.n_cells == 2
    assert m.by_status[COVERED] == 1
    assert m.by_status[CONFIDENT_ABSENCE] == 1
    assert m.by_status[POSSIBLE_ABSENCE] == 0
    assert m.by_status[UNKNOWN] == 0

    cov = m.cell(NICKEL, "flow_velocity")
    absent = m.cell(NICKEL, "recovery")
    assert cov is not None and cov.status == COVERED and cov.confidence_of_absence == 0.0
    assert absent is not None and absent.status == CONFIDENT_ABSENCE
    assert absent.confidence_of_absence == pytest.approx(CONF_07, abs=1e-3)
    # mean over the two numeric cells: (0.0 + 0.7692) / 2 = 0.3846
    assert m.summary.mean_confidence == pytest.approx((0.0 + CONF_07) / 2, abs=1e-3)


def test_status_counts_sum_to_n_cells(store: KuzuGraphStore) -> None:
    # electrometallurgy has exactly 2 materials (nickel, catholyte) × 8 default
    # properties = 16 cells; 4 are COVERED (current_density, flow_velocity ×2),
    # the remaining 12 are confident absences (§25.11 Критерий приёмки).
    m = build_absence_map(store, domain="electrometallurgy")
    assert len(m.cells) == 16
    assert sum(m.by_status.values()) == len(m.cells)
    assert sum(m.by_status.values()) == m.summary.n_cells
    assert m.summary.n_covered == 4
    assert m.summary.n_confident_absence == 12
    assert m.summary.n_possible_absence == 0
    assert m.summary.n_unknown == 0
    # every status key from the vocabulary is present
    assert set(m.by_status) == set(STATUSES)
    # 12 cells at 0.7692 and 4 at 0.0 → mean 0.5769
    assert m.summary.mean_confidence == pytest.approx(12 * CONF_07 / 16, abs=1e-3)


def test_mean_confidence_in_unit_range(store: KuzuGraphStore) -> None:
    m = build_absence_map(store, domain="electrometallurgy")
    assert 0.0 <= m.summary.mean_confidence <= 1.0
    # and each per-property mean is also a proper probability
    for pc in m.by_property.values():
        assert 0.0 <= pc.mean_confidence <= 1.0


def test_by_property_breakdown_present(store: KuzuGraphStore) -> None:
    m = build_absence_map(store, domain="electrometallurgy")
    # every default property applied to both materials → a 2-cell slice each
    assert len(m.by_property) == len(m.properties)
    for pc in m.by_property.values():
        assert pc.n_cells == 2
        assert sum(pc.by_status.values()) == pc.n_cells
    # recovery: nobody measured it for nickel/catholyte → 2 confident absences
    rec = m.by_property["recovery"]
    assert rec.by_status[CONFIDENT_ABSENCE] == 2
    assert rec.mean_confidence == pytest.approx(CONF_07, abs=1e-3)
    # current_density: reachable for both materials → 2 covered, mean 0.0
    cd = m.by_property["current_density"]
    assert cd.by_status[COVERED] == 2
    assert cd.mean_confidence == 0.0


def test_by_domain_aggregation(store: KuzuGraphStore) -> None:
    # cross-domain grid: nickel (electrometallurgy) + mine water (water_treatment).
    # water has concentration data (COVERED); everything else is a confident absence.
    m = build_absence_map(
        store, materials=[NICKEL, WATER], properties=["concentration", "recovery"]
    )
    assert len(m.cells) == 4
    assert set(m.by_domain) == {"electrometallurgy", "water_treatment"}
    assert m.by_domain["water_treatment"][COVERED] == 1
    assert m.by_domain["water_treatment"][CONFIDENT_ABSENCE] == 1
    assert m.by_domain["electrometallurgy"][CONFIDENT_ABSENCE] == 2
    assert m.by_domain["electrometallurgy"][COVERED] == 0
    # per-domain counts partition the grid
    total = sum(v for bucket in m.by_domain.values() for v in bucket.values())
    assert total == len(m.cells)


def test_low_recall_yields_unknown_excluded_from_mean(store: KuzuGraphStore) -> None:
    # With a barely-detecting extractor (recall 0.1) a null observation is
    # uninformative → UNKNOWN; the string sentinel must not skew mean_confidence.
    m = build_absence_map(
        store,
        materials=[NICKEL],
        properties=["recovery", "flow_velocity"],
        recall=ExtractorRecall(default=0.1),
    )
    assert m.by_status[UNKNOWN] == 1  # recovery
    assert m.by_status[COVERED] == 1  # flow_velocity (evidence exists regardless of recall)
    assert m.summary.n_confident_absence == 0
    assert m.summary.n_possible_absence == 0
    # only the covered (0.0) cell is numeric → mean is exactly 0.0, still in range
    assert m.summary.mean_confidence == 0.0
    assert sum(m.by_status.values()) == len(m.cells) == 2


def test_as_dict_is_json_serialisable(store: KuzuGraphStore) -> None:
    m = build_absence_map(store, domain="electrometallurgy")
    d = m.as_dict()
    assert set(d) >= {"by_status", "by_property", "by_domain", "summary", "cells"}
    assert d["n_cells"] == len(m.cells) == d["summary"]["n_cells"]
    assert len(d["cells"]) == len(m.cells)
    # round-trips through JSON without raising (floats + "unknown" sentinel are ok)
    text = json.dumps(d, ensure_ascii=False)
    assert '"by_status"' in text
    reloaded = json.loads(text)
    assert reloaded["summary"]["n_confident_absence"] == m.summary.n_confident_absence
