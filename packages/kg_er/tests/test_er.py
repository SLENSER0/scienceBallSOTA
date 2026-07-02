"""Entity-resolution pipeline tests (§8): features, deterministic scoring,
decision engine, property mapping. Deterministic + fast (no Splink EM)."""

from __future__ import annotations

from kg_er.comparisons import text
from kg_er.deterministic import deterministic_clusters, pair_score

from kg_er import (
    PropertyMapper,
    build_er_frame,
    decide,
    default_vocabulary,
    get_model,
    resolve,
    thresholds_for,
)
from kg_schema.enums import MatchDecision

MATERIALS = [
    {"unique_id": "m1", "name": "сплав Al-Cu 2024", "formula": "Al4Cu1Mg"},
    {"unique_id": "m2", "name": "Al-Cu 2024 alloy", "formula": "Al4Cu1Mg"},
    {"unique_id": "m3", "name": "2024", "formula": "Al4Cu1Mg"},
    {"unique_id": "m4", "name": "медь М1", "formula": "Cu"},
    {"unique_id": "m5", "name": "copper M1", "formula": "Cu"},
]


# ---- feature engineering -------------------------------------------------
def test_build_er_frame_deterministic() -> None:
    a = build_er_frame("Material", MATERIALS)
    b = build_er_frame("Material", list(reversed(MATERIALS)))
    assert list(a["unique_id"]) == list(b["unique_id"])  # stable sort
    assert set(a.columns) >= {"unique_id", "name_clean", "normalized_formula", "element_key"}


def test_all_specs_build() -> None:
    for t in ("Material", "Alloy", "Equipment", "Person", "Lab", "ResearchTeam"):
        spec = get_model(t)
        assert spec.comparisons and spec.blocking_rules


# ---- deterministic resolution (the per-document use case) ----------------
def test_material_merges_variants_but_not_copper() -> None:
    r = resolve("Material", MATERIALS)
    assert r.model_card["backend"] == "deterministic"
    clusters = {frozenset(c.members) for c in r.clusters if len(c.members) > 1}
    assert frozenset({"m1", "m2", "m3"}) in clusters
    assert frozenset({"m4", "m5"}) in clusters
    # precision guard: copper never merges with the Al-Cu alloy
    assert not any({"m1", "m4"} <= set(c.members) for c in r.clusters)


def test_element_key_mismatch_blocks_merge() -> None:
    x = {"unique_id": "a", "name_clean": "steel", "element_key": "Fe", "normalized_formula": ""}
    y = {"unique_id": "b", "name_clean": "steel", "element_key": "Cu", "normalized_formula": ""}
    assert pair_score("Material", x, y) < 0.5


def test_person_orcid_auto_merge() -> None:
    people = [
        {"unique_id": "p1", "name": "Иванов И.И.", "orcid": "0000-0001", "email": "a@misis.ru"},
        {"unique_id": "p2", "name": "Иван Иванов", "orcid": "0000-0001"},
        {"unique_id": "p3", "name": "Петров П.П.", "email": "b@misis.ru"},
    ]
    r = resolve("Person", people)
    merged = [c for c in r.clusters if len(c.members) > 1]
    assert len(merged) == 1 and set(merged[0].members) == {"p1", "p2"}
    assert merged[0].max_probability >= 0.95


def test_lab_abbreviation_subset_merge() -> None:
    labs = [
        {"unique_id": "l1", "org": "НИТУ МИСИС", "city": "Москва", "country": "Россия"},
        {"unique_id": "l2", "org": "МИСИС", "city": "Москва", "country": "Россия"},
        {"unique_id": "l3", "org": "УрФУ", "city": "Екатеринбург"},
    ]
    r = resolve("Lab", labs)
    merged = [c for c in r.clusters if len(c.members) > 1]
    assert len(merged) == 1 and set(merged[0].members) == {"l1", "l2"}


def test_singleton_and_trivial_inputs() -> None:
    assert resolve("Material", []).n_input == 0
    r1 = resolve("Material", [MATERIALS[0]])
    assert r1.n_input == 1 and r1.proposals == []


# ---- decision engine -----------------------------------------------------
def test_thresholds_and_decide() -> None:
    auto, review = thresholds_for("Material")
    assert 0 < review < auto <= 1
    assert decide("Material", auto) is MatchDecision.AUTO_MERGE
    assert decide("Material", review) is MatchDecision.REVIEW_NEEDED
    assert decide("Material", 0.0) is MatchDecision.SEPARATE


def test_reviewed_canonical_downgrades_auto_merge() -> None:
    # a locked canonical in the cluster forces human confirmation (§8.9)
    r = resolve("Material", MATERIALS, reviewed_ids=frozenset({"m1"}))
    al = next(p for p in r.proposals if "m1" in p.members)
    assert al.blocked_by_review and al.decision is MatchDecision.REVIEW_NEEDED


def test_deterministic_clusters_covers_all_ids() -> None:
    rows = build_er_frame("Material", MATERIALS).to_dict("records")
    clusters = deterministic_clusters("Material", rows, threshold=0.5)
    covered = {m for c in clusters for m in c.members}
    assert covered == {m["unique_id"] for m in MATERIALS}


# ---- property mapping (§8.6) ---------------------------------------------
def test_property_mapper_exact_and_fuzzy() -> None:
    mapper = PropertyMapper(default_vocabulary())
    assert mapper.map("твердость").canonical_id == "prop:hardness"
    assert mapper.map("HV", unit="HV").unit_ok
    novel = mapper.map("совершенно новый параметр zzz")
    assert novel.status == "review_needed"


def test_property_mapper_unit_incompatible() -> None:
    mapper = PropertyMapper(default_vocabulary())
    m = mapper.map("hardness", unit="MPa")  # MPa not in hardness allowed_units
    assert m.canonical_id == "prop:hardness" and not m.unit_ok


# ---- text comparisons ----------------------------------------------------
def test_text_helpers() -> None:
    assert text.clean_text("Al-Cu 2024 (сплав)!") == "al-cu 2024 сплав"
    _, family, _ = text.split_person_name("Ivanov I.I.")
    assert family == "ivanov"
    assert text.designation_code("Alloy AA6061-T6").startswith("aa6061")
    assert text.email_domain("a@MISIS.ru") == "misis.ru"


# ---- Splink backend smoke (regression for the trained path) --------------
def test_splink_backend_runs() -> None:
    # forcing backend="splink" exercises train_linker + predict_clusters; on tiny
    # data EM may not fully converge, so we assert only that it runs and labels.
    r = resolve("Material", MATERIALS, backend="splink")
    assert r.model_card["backend"] in {"splink", "deterministic_fallback"}
    assert r.n_input == 5
