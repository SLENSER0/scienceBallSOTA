"""Metal distribution-coefficient analysis over the seed graph (§24.7).

Hand-checked against ``kg_retrievers.seed.build_seed_graph``:
- four ``distribution_coefficient`` Measurements: Au(0.95)/Ag(0.9)/PGM(0.98) matte↔
  smelter-slag (§seed-3) and Cu(25.0) matte↔flash-slag (§seed-7);
- copper matte is ``material_class='matte'``, both slags ``'slag'`` → every
  coefficient partitions the pair ("matte","slag");
- the Cu coefficient carries Evidence ``paper:flash-2021:fs-cu`` on its edges and
  a ``SUPPORTED_BY`` Evidence node.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.distribution_analysis import (
    PHASE_CLASSES,
    analyze_distribution,
    partition_ratio,
)
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph

CU_COEFF = make_id("Measurement", "cu distribution matte slag")
CU_MATTE = make_id("Material", "copper matte")
FLASH_SLAG = make_id("Material", "flash smelting slag")
FS_EVIDENCE = make_id("Evidence", "paper:flash-2021:fs-cu")


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(s)
    yield s
    s.close()


@pytest.fixture
def empty_store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _cu(report):  # type: ignore[no-untyped-def]
    return next(c for c in report.coefficients if c.measurement_id == CU_COEFF)


def test_analyze_finds_at_least_one_coefficient(store: KuzuGraphStore) -> None:
    report = analyze_distribution(store)
    assert report.count >= 1
    # the seed defines exactly four distribution_coefficient measurements
    assert len(report.coefficients) == 4
    ids = {c.measurement_id for c in report.coefficients}
    assert CU_COEFF in ids


def test_cu_matte_slag_value_is_25(store: KuzuGraphStore) -> None:
    cu = _cu(analyze_distribution(store))
    assert cu.value == 25.0
    # exactly one coefficient in the seed carries the L(Cu) ≈ 25 value
    values = [c.value for c in analyze_distribution(store).coefficients]
    assert values.count(25.0) == 1


def test_cu_phases_include_matte_and_slag(store: KuzuGraphStore) -> None:
    cu = _cu(analyze_distribution(store))
    assert "matte" in cu.phases
    assert "slag" in cu.phases
    assert set(cu.phases) <= PHASE_CLASSES
    # phase material ids resolve to copper matte + the flash-smelting slag
    assert CU_MATTE in cu.phase_ids
    assert FLASH_SLAG in cu.phase_ids


def test_by_phase_pair_is_keyed_by_matte_slag(store: KuzuGraphStore) -> None:
    report = analyze_distribution(store)
    assert "matte|slag" in report.by_phase_pair
    # all four seed coefficients partition matte vs slag
    all_ids = {c.measurement_id for c in report.coefficients}
    assert set(report.by_phase_pair["matte|slag"]) == all_ids
    assert CU_COEFF in report.by_phase_pair["matte|slag"]


def test_cu_coefficient_has_linked_evidence(store: KuzuGraphStore) -> None:
    cu = _cu(analyze_distribution(store))
    assert cu.evidence_ids  # non-empty
    assert FS_EVIDENCE in cu.evidence_ids
    # as_dict exposes the required coefficient shape
    d = cu.as_dict()
    assert {"measurement_id", "value", "phases", "evidence_ids"} <= set(d)
    assert d["value"] == 25.0
    assert d["evidence_ids"] == list(cu.evidence_ids)


def test_partition_ratio_helper() -> None:
    # L(Cu)=25 → ~96% reports to the enriched (matte) phase
    r = partition_ratio(25.0)
    assert r is not None
    assert abs(r - 25.0 / 26.0) < 1e-9
    assert partition_ratio(None) is None
    assert partition_ratio(-1.0) is None
    assert partition_ratio(0.0) == 0.0


def test_domain_scoping_and_report_as_dict(store: KuzuGraphStore) -> None:
    # every seed coefficient lives in pyrometallurgy → domain scope keeps all four
    pyro = analyze_distribution(store, domain="pyrometallurgy")
    assert pyro.count == 4
    d = pyro.as_dict()
    assert d["count"] == 4
    assert set(d) == {"count", "coefficients", "by_phase_pair"}
    assert "matte|slag" in d["by_phase_pair"]


def test_empty_and_absent_domain_are_graceful(
    store: KuzuGraphStore, empty_store: KuzuGraphStore
) -> None:
    # a graph with no distribution coefficients yields an empty report
    empty = analyze_distribution(empty_store)
    assert empty.count == 0
    assert empty.coefficients == ()
    assert empty.by_phase_pair == {}
    assert empty.as_dict()["coefficients"] == []
    # a domain that exists nowhere is equally graceful (no error, empty result)
    absent = analyze_distribution(store, domain="no_such_domain")
    assert absent.count == 0
    assert absent.by_phase_pair == {}
