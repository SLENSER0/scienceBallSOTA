"""3D material × regime × property coverage matrix over a hand-built graph (§15.5).

Builds a tiny store (the seed carries no Measurement→ProcessingRegime triples) with
two materials × two regimes and four measurements:

    m1 recovery  ABOUT_MATERIAL α  ABOUT_REGIME leaching  verified   conf 0.9
    m2 recovery  ABOUT_MATERIAL α  ABOUT_REGIME leaching  unverified conf 0.4
    m3 recovery  ABOUT_MATERIAL α  ABOUT_REGIME smelting  verified   conf 0.85
    m4 recovery  ABOUT_MATERIAL β  ABOUT_REGIME smelting  unverified conf 0.9
    Gap g1 (property=concentration)  ABOUT_MATERIAL β  ABOUT_REGIME leaching

Hand-checked expectations (no filters):
- α × leaching × recovery is covered by m1+m2 → evidence 2, verified 1;
- α × smelting × recovery is covered by m3 → evidence 1, verified 1;
- β × smelting × recovery is covered by m4 → evidence 1, verified 0;
- β × leaching × concentration is absent but carries gap g1;
- axes: materials [α, β], regimes [leaching, smelting], properties [concentration, recovery].
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.coverage_matrix_3d import (
    ABSENT,
    COVERED,
    Cell,
    Matrix3D,
    build_material_regime_property_matrix,
)
from kg_retrievers.graph_store import KuzuGraphStore

MAT_A = make_id("Material", "alpha")
MAT_B = make_id("Material", "beta")
REG_LEACH = make_id("ProcessingRegime", "leaching")
REG_SMELT = make_id("ProcessingRegime", "smelting")
GAP1 = make_id("Gap", "beta leaching concentration gap")


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _build(s)
    yield s
    s.close()


def _build(s: KuzuGraphStore) -> None:
    s.upsert_node(MAT_A, "Material", name="alpha")
    s.upsert_node(MAT_B, "Material", name="beta")
    s.upsert_node(REG_LEACH, "ProcessingRegime", name="leaching")
    s.upsert_node(REG_SMELT, "ProcessingRegime", name="smelting")

    def meas(mid: str, matid: str, regid: str, *, verified: bool, conf: float) -> None:
        nid = make_id("Measurement", mid)
        s.upsert_node(
            nid, "Measurement", property_name="recovery", verified=verified, confidence=conf
        )
        s.upsert_edge(nid, matid, "ABOUT_MATERIAL", confidence=conf)
        s.upsert_edge(nid, regid, "ABOUT_REGIME", confidence=conf)

    meas("m1", MAT_A, REG_LEACH, verified=True, conf=0.9)
    meas("m2", MAT_A, REG_LEACH, verified=False, conf=0.4)
    meas("m3", MAT_A, REG_SMELT, verified=True, conf=0.85)
    meas("m4", MAT_B, REG_SMELT, verified=False, conf=0.9)

    # A recorded gap for an uncovered triple: β × leaching × concentration.
    s.upsert_node(GAP1, "Gap", name="нет данных: концентрация", property_name="concentration")
    s.upsert_edge(GAP1, MAT_B, "ABOUT_MATERIAL", confidence=0.9)
    s.upsert_edge(GAP1, REG_LEACH, "ABOUT_REGIME", confidence=0.9)


def _by_key(matrix: Matrix3D) -> dict[tuple[str, str, str], Cell]:
    return {(c.material_id, c.regime_id, c.property_id): c for c in matrix.cells}


# -- covered triple --------------------------------------------------------
def test_covered_triple_has_evidence(store: KuzuGraphStore) -> None:
    matrix = build_material_regime_property_matrix(store)
    cells = _by_key(matrix)

    covered = cells[(MAT_A, REG_LEACH, "recovery")]
    assert covered.status == COVERED
    assert covered.is_covered is True
    assert covered.evidence_count == 2  # m1 + m2 both link α × leaching × recovery
    assert covered.verified_count == 1  # only m1 is verified
    assert covered.has_gap is False and covered.gap_ids == ()

    # smelting is covered by exactly one (verified) measurement, m3
    single = cells[(MAT_A, REG_SMELT, "recovery")]
    assert single.status == COVERED
    assert single.evidence_count == 1 and single.verified_count == 1

    assert matrix.covered_count == 3  # α×leach×rec, α×smelt×rec, β×smelt×rec
    assert matrix.absent_count == len(matrix.cells) - 3


# -- absent triple with a recorded gap -------------------------------------
def test_absent_triple_flags_gap(store: KuzuGraphStore) -> None:
    matrix = build_material_regime_property_matrix(store)
    cells = _by_key(matrix)

    gap_cell = cells[(MAT_B, REG_LEACH, "concentration")]
    assert gap_cell.status == ABSENT
    assert gap_cell.evidence_count == 0 and gap_cell.verified_count == 0
    assert gap_cell.has_gap is True
    assert gap_cell.gap_ids == (GAP1,)

    # an absent cell with no gap stays clean
    plain = cells[(MAT_B, REG_LEACH, "recovery")]
    assert plain.status == ABSENT
    assert plain.has_gap is False and plain.gap_ids == ()

    assert matrix.gap_count == 1  # exactly one flagged cell in the whole cube


# -- min_confidence filter -------------------------------------------------
def test_min_confidence_drops_low_conf(store: KuzuGraphStore) -> None:
    # threshold 0.5 drops m2 (conf 0.4); m1 (0.9) survives → still covered, evidence 1
    filtered = _by_key(build_material_regime_property_matrix(store, min_confidence=0.5))
    cell = filtered[(MAT_A, REG_LEACH, "recovery")]
    assert cell.status == COVERED
    assert cell.evidence_count == 1  # m2 dropped
    assert cell.verified_count == 1  # m1 remains, verified

    # threshold 0.95 drops both m1 (0.9) and m2 (0.4) → the cell flips to absent
    strict = _by_key(build_material_regime_property_matrix(store, min_confidence=0.95))
    gone = strict[(MAT_A, REG_LEACH, "recovery")]
    assert gone.status == ABSENT
    assert gone.evidence_count == 0 and gone.verified_count == 0


# -- verified_only filter --------------------------------------------------
def test_verified_only_counts(store: KuzuGraphStore) -> None:
    default = _by_key(build_material_regime_property_matrix(store))
    verified = _by_key(build_material_regime_property_matrix(store, verified_only=True))

    # β × smelting × recovery is covered by m4 alone, which is UNverified:
    # it is covered by default but flips to absent under verified_only.
    key = (MAT_B, REG_SMELT, "recovery")
    assert default[key].status == COVERED
    assert default[key].evidence_count == 1 and default[key].verified_count == 0
    assert verified[key].status == ABSENT
    assert verified[key].evidence_count == 0 and verified[key].verified_count == 0

    # α × leaching × recovery drops the unverified m2: evidence 2 → 1, still covered
    mix = (MAT_A, REG_LEACH, "recovery")
    assert default[mix].evidence_count == 2
    assert verified[mix].status == COVERED
    assert verified[mix].evidence_count == 1 and verified[mix].verified_count == 1


# -- regimes are isolated --------------------------------------------------
def test_regimes_are_isolated(store: KuzuGraphStore) -> None:
    cells = _by_key(build_material_regime_property_matrix(store))

    # β has a recovery measurement under smelting but none under leaching:
    # coverage must not leak across regimes for the same material + property.
    assert cells[(MAT_B, REG_SMELT, "recovery")].status == COVERED
    assert cells[(MAT_B, REG_LEACH, "recovery")].status == ABSENT

    # α is covered independently under each regime by its own measurements
    assert cells[(MAT_A, REG_LEACH, "recovery")].status == COVERED
    assert cells[(MAT_A, REG_SMELT, "recovery")].status == COVERED


# -- dims list the axes ----------------------------------------------------
def test_dims_list_the_axes(store: KuzuGraphStore) -> None:
    matrix = build_material_regime_property_matrix(store)
    assert matrix.materials == (MAT_A, MAT_B)  # sorted node ids
    assert matrix.regimes == (REG_LEACH, REG_SMELT)
    # property axis unions Measurement (recovery) + Gap (concentration) names, sorted
    assert matrix.properties == ("concentration", "recovery")

    # the cells are the full cross product of the three axes
    assert len(matrix.cells) == 2 * 2 * 2
    assert matrix.covered_count + matrix.absent_count == len(matrix.cells)

    dims = matrix.as_dict()["dims"]
    assert dims == {
        "materials": [MAT_A, MAT_B],
        "regimes": [REG_LEACH, REG_SMELT],
        "properties": ["concentration", "recovery"],
    }


# -- as_dict shape ---------------------------------------------------------
def test_as_dict_shape(store: KuzuGraphStore) -> None:
    d = build_material_regime_property_matrix(store).as_dict()
    assert set(d) == {"cells", "dims"}
    assert isinstance(d["cells"], list) and isinstance(d["dims"], dict)
    assert set(d["dims"]) == {"materials", "regimes", "properties"}
    assert len(d["cells"]) == 8

    cell = next(
        c
        for c in d["cells"]
        if (c["material_id"], c["regime_id"], c["property_id"]) == (MAT_A, REG_LEACH, "recovery")
    )
    assert set(cell) == {
        "material_id",
        "regime_id",
        "property_id",
        "status",
        "evidence_count",
        "verified_count",
        "has_gap",
        "gap_ids",
    }
    assert cell["status"] == COVERED
    assert cell["evidence_count"] == 2 and cell["verified_count"] == 1
    assert cell["has_gap"] is False and cell["gap_ids"] == []

    # the gap cell round-trips its gap ids as a list
    gap_cell = next(
        c
        for c in d["cells"]
        if (c["material_id"], c["regime_id"], c["property_id"])
        == (MAT_B, REG_LEACH, "concentration")
    )
    assert gap_cell["has_gap"] is True and gap_cell["gap_ids"] == [GAP1]
