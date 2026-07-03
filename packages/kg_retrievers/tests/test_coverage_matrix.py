"""Coverage-matrix aggregations over the seed graph (§15.5).

Hand-checked against ``kg_retrievers.seed.build_seed_graph``:
- 8 Material nodes; nickel reaches 2 verified flow_velocity measurements (≤2 hops);
- Paper years 2019,2020,2021(×2),2022,2023 → 6 papers total;
- Measurements SUPPORTED_BY a paper: 2021→2 (fv, l_cu), 2023→3 (Au/Ag/PGM partition);
- exactly one seed Gap, owned by domain "hydrometallurgy" (lab: гидрометаллургия).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.confidence_of_absence import AbsenceAnalyzer
from kg_retrievers.coverage_matrix import (
    MATRIX_ABSENT,
    MATRIX_COVERED,
    aggregate_gaps_by_owner,
    build_coverage_matrix,
    build_coverage_timeline,
)
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph

NICKEL = make_id("Material", "nickel")
SEED_GAP = make_id("Gap", "cold heap leaching nickel gap")
HYDRO_LAB = make_id("Lab", "hydrometallurgy lab")


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(s)
    yield s
    s.close()


# -- coverage matrix -------------------------------------------------------
def test_matrix_covered_and_absent_cells(store: KuzuGraphStore) -> None:
    # nickel × flow_velocity is covered by 2 verified measurements (fv, fv2);
    # nickel × recovery has no evidence anywhere near nickel → absent.
    matrix = build_coverage_matrix(
        store, materials=[NICKEL], properties=["flow_velocity", "recovery"]
    )
    assert matrix.materials == (NICKEL,)
    assert matrix.properties == ("flow_velocity", "recovery")
    assert len(matrix.cells) == 2

    by_prop = {c.property_name: c for c in matrix.cells}
    fv = by_prop["flow_velocity"]
    assert fv.material_id == NICKEL
    assert fv.status == MATRIX_COVERED
    assert fv.is_covered is True
    assert fv.evidence_count == 2
    assert fv.verified_count == 2  # both seed measurements are verified

    rec = by_prop["recovery"]
    assert rec.status == MATRIX_ABSENT
    assert rec.evidence_count == 0
    assert rec.verified_count == 0

    assert matrix.covered_count == 1
    assert matrix.absent_count == 1


def test_matrix_default_axes_cover_all_materials(store: KuzuGraphStore) -> None:
    matrix = build_coverage_matrix(store)  # materials=None, properties=None
    assert len(matrix.materials) == 8  # eight Material nodes in the seed
    # full cross product, and covered + absent partitions every cell
    assert len(matrix.cells) == len(matrix.materials) * len(matrix.properties)
    assert matrix.covered_count + matrix.absent_count == len(matrix.cells)
    for c in matrix.cells:
        assert c.material_id and c.property_name
        assert c.status in {MATRIX_COVERED, MATRIX_ABSENT}
        assert isinstance(c.verified_count, int) and c.verified_count >= 0
        # verified is a subset of all evidence, and covered ⇔ some evidence
        assert c.verified_count <= c.evidence_count
        assert (c.status == MATRIX_COVERED) == (c.evidence_count > 0)


def test_matrix_as_dict_shape(store: KuzuGraphStore) -> None:
    matrix = build_coverage_matrix(store, materials=[NICKEL], properties=["flow_velocity"])
    d = matrix.as_dict()
    assert d["materials"] == [NICKEL]
    assert d["properties"] == ["flow_velocity"]
    assert d["covered_count"] == 1 and d["absent_count"] == 0
    assert len(d["cells"]) == 1
    cell = d["cells"][0]
    assert set(cell) == {
        "material_id",
        "material_name",
        "property_name",
        "status",
        "evidence_count",
        "verified_count",
    }
    assert cell["status"] == MATRIX_COVERED


def test_matrix_empty_filters_are_graceful(store: KuzuGraphStore) -> None:
    empty_mats = build_coverage_matrix(store, materials=[], properties=["recovery"])
    assert empty_mats.materials == ()
    assert empty_mats.cells == ()
    assert empty_mats.covered_count == 0 and empty_mats.absent_count == 0

    empty_props = build_coverage_matrix(store, materials=[NICKEL], properties=[])
    assert empty_props.properties == ()
    assert empty_props.cells == ()


# -- gaps by owner ---------------------------------------------------------
def test_gaps_by_owner_seed_single_group(store: KuzuGraphStore) -> None:
    groups = aggregate_gaps_by_owner(store)
    assert len(groups) == 1
    g = groups[0]
    assert g.owner == "hydrometallurgy"
    assert g.gap_count == 1
    assert g.gap_ids == (SEED_GAP,)
    # the hydrometallurgy lab is attached as the owning lab
    assert g.lab_id == HYDRO_LAB
    assert g.lab_name == "Лаборатория гидрометаллургии"
    # as_dict round-trip
    assert g.as_dict()["gap_count"] == 1


def test_gaps_by_owner_partition_sums_to_total(store: KuzuGraphStore) -> None:
    # materialize confidence-of-absence gaps in electrometallurgy (no g.domain;
    # owner resolved via the ABOUT→Material domain), then check the partition.
    AbsenceAnalyzer(store).scan_absence(domain="electrometallurgy")
    total = store.rows("MATCH (g:Node) WHERE g.label='Gap' RETURN count(g)")[0][0]
    assert total > 1  # seed gap + newly materialized absences

    groups = aggregate_gaps_by_owner(store)
    owners = {g.owner for g in groups}
    assert "hydrometallurgy" in owners
    assert "electrometallurgy" in owners
    # groups partition every Gap node exactly once
    assert sum(g.gap_count for g in groups) == total
    all_ids = [gid for g in groups for gid in g.gap_ids]
    assert len(all_ids) == total == len(set(all_ids))
    # the electrometallurgy owner has no lab in the seed → lab fields are None
    electro = next(g for g in groups if g.owner == "electrometallurgy")
    assert electro.lab_id is None and electro.lab_name is None
    assert electro.gap_count >= 1


# -- coverage timeline -----------------------------------------------------
def test_timeline_year_ordered_with_expected_counts(store: KuzuGraphStore) -> None:
    points = build_coverage_timeline(store)
    years = [p.year for p in points]
    assert years == [2019, 2020, 2021, 2022, 2023]  # ascending, one point per year
    assert years == sorted(years)

    by_year = {p.year: p for p in points}
    # 2021 has two papers (ni-ew + flash), each 2 measurements SUPPORTED_BY it
    assert by_year[2021].paper_count == 2
    assert by_year[2021].measurement_count == 2
    # 2023 (pgm) dates the three Au/Ag/PGM partition measurements
    assert by_year[2023].measurement_count == 3
    # remaining years carry exactly one paper each and no dated measurements
    for yr in (2019, 2020, 2022):
        assert by_year[yr].paper_count == 1
        assert by_year[yr].measurement_count == 0

    assert sum(p.paper_count for p in points) == 6
    assert sum(p.measurement_count for p in points) == 5
    for p in points:
        assert p.paper_count >= 0 and p.measurement_count >= 0 and p.gap_count >= 0
        assert p.gap_count == 0  # no seed Gap is SUPPORTED_BY a dated Paper
        assert set(p.as_dict()) == {"year", "paper_count", "measurement_count", "gap_count"}
